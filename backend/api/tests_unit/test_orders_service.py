"""Unit test cho api/services/orders.py."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from ..models import Category, MenuItem, Order, OrderItem, Payment, Promotion, Table
from ..services.orders import compute_discount, promotion_base, recalc_order, release_table_if_idle


class OrderFixtureMixin:
    def setUp(self):
        self.table = Table.objects.create(area='A')
        cat = Category.objects.create(name='Chính')
        self.pho = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('100000'))
        self.tea = MenuItem.objects.create(category=cat, name='Trà', price=Decimal('20000'))
        self.order = Order.objects.create(table=self.table)
        OrderItem.objects.create(order=self.order, menu_item=self.pho, quantity=2, unit_price=self.pho.price)  # 200k
        OrderItem.objects.create(order=self.order, menu_item=self.tea, quantity=5, unit_price=self.tea.price)  # 100k

    def promo(self, code='P', kind='percent', value=10, item=None, active=True, start=None, end=None):
        now = timezone.now()
        return Promotion.objects.create(
            code=code, discount_type=kind, value=Decimal(value), menu_item=item, is_active=active,
            start_date=start or now - timedelta(days=1), end_date=end or now + timedelta(days=1))


class ComputeDiscountTests(OrderFixtureMixin, TestCase):
    def test_no_promotion_gives_zero_discount(self):
        """Không có mã -> giảm 0."""
        self.assertEqual(compute_discount(self.order, None), Decimal(0))

    def test_percent_discount_applies_to_whole_order(self):
        """Mã 10% trên đơn 300k -> giảm 30k."""
        self.assertEqual(compute_discount(self.order, self.promo(value=10)), Decimal(30000))

    def test_fixed_discount_is_returned_as_is(self):
        """Mã cố định 50k trên đơn 300k -> giảm đúng 50k."""
        self.assertEqual(compute_discount(self.order, self.promo(kind='fixed', value=50000)), Decimal(50000))

    def test_fixed_discount_never_exceeds_order_total(self):
        """Mã cố định 500k lớn hơn tổng 300k -> chỉ giảm 300k."""
        self.assertEqual(compute_discount(self.order, self.promo(kind='fixed', value=500000)), Decimal(300000))

    def test_hundred_percent_discount_equals_base(self):
        """Mã 100% -> giảm đúng bằng tổng."""
        self.assertEqual(compute_discount(self.order, self.promo(value=100)), Decimal(300000))

    def test_percent_over_100_is_capped_at_base(self):
        """Dữ liệu sai 150% vẫn bị chặn ở mức tổng tiền."""
        self.assertEqual(compute_discount(self.order, self.promo(value=150)), Decimal(300000))

    def test_item_promotion_only_counts_matching_lines(self):
        """Mã gắn món Phở 50% -> chỉ tính trên 200k của Phở, giảm 100k."""
        promo = self.promo(value=50, item=self.pho)
        self.assertEqual(promotion_base(self.order, promo), Decimal(200000))
        self.assertEqual(compute_discount(self.order, promo), Decimal(100000))

    def test_item_fixed_promotion_capped_by_item_base(self):
        """Mã cố định 150k gắn món Trà (100k) -> giảm tối đa 100k."""
        self.assertEqual(compute_discount(self.order, self.promo(kind='fixed', value=150000, item=self.tea)), Decimal(100000))

    def test_item_promotion_without_matching_line_is_zero(self):
        """Mã gắn món không có trong đơn -> giảm 0."""
        other = MenuItem.objects.create(name='Bún', price=Decimal('1000'))
        self.assertEqual(compute_discount(self.order, self.promo(item=other)), Decimal(0))

    def test_percent_discount_is_rounded_to_whole_vnd(self):
        """Kết quả giảm làm tròn về đồng (không có phần thập phân)."""
        OrderItem.objects.create(order=self.order, menu_item=self.tea, quantity=1, unit_price=Decimal('3'))
        result = compute_discount(self.order, self.promo(value=33))
        self.assertEqual(result, result.quantize(Decimal(1)))
        self.assertEqual(result, Decimal(99001))

    def test_compute_discount_does_not_check_validity_window(self):
        """compute_discount chỉ tính tiền; kiểm tra hạn/kích hoạt nằm ở tầng view (ghi nhận hành vi hiện tại)."""
        now = timezone.now()
        expired = self.promo(code='OLD', start=now - timedelta(days=5), end=now - timedelta(days=1))
        self.assertEqual(compute_discount(self.order, expired), Decimal(30000))


class RecalcOrderTests(OrderFixtureMixin, TestCase):
    def test_recalc_sets_subtotal_and_total_without_promotion(self):
        """Không mã: tạm tính = tổng = 300k, giảm 0."""
        recalc_order(self.order)
        self.order.refresh_from_db()
        self.assertEqual((self.order.subtotal_amount, self.order.discount_amount, self.order.total_amount),
                         (Decimal(300000), Decimal(0), Decimal(300000)))

    def test_recalc_recomputes_percent_after_item_removed(self):
        """Xoá dòng Trà, mã 10% được tính lại trên 200k -> giảm 20k, tổng 180k."""
        self.order.promotion = self.promo(value=10)
        self.order.save()
        OrderItem.objects.filter(menu_item=self.tea).delete()
        recalc_order(self.order)
        self.order.refresh_from_db()
        self.assertEqual((self.order.discount_amount, self.order.total_amount), (Decimal(20000), Decimal(180000)))

    def test_recalc_caps_fixed_discount_and_total_never_negative(self):
        """Mã cố định lớn hơn tổng -> tổng = 0, không âm."""
        self.order.promotion = self.promo(kind='fixed', value=999999)
        self.order.save()
        recalc_order(self.order)
        self.assertEqual(self.order.total_amount, Decimal(0))

    def test_recalc_empty_order_is_zero(self):
        """Đơn không còn món -> mọi số tiền bằng 0."""
        OrderItem.objects.filter(order=self.order).delete()
        recalc_order(self.order)
        self.assertEqual((self.order.subtotal_amount, self.order.total_amount), (0, 0))

    def test_recalc_updates_pending_cash_payment_amount(self):
        """Thanh toán chờ (tiền mặt) được cập nhật số tiền mới."""
        pay = Payment.objects.create(order=self.order, method='cash', amount=Decimal(1), transaction_id='T1')
        recalc_order(self.order)
        pay.refresh_from_db()
        self.assertEqual(pay.amount, Decimal(300000))

    def test_recalc_resets_vnpay_link_when_amount_changes(self):
        """Thanh toán VNPay chờ: đổi số tiền -> xoá link/ngày tạo cũ để buộc tạo link mới."""
        pay = Payment.objects.create(order=self.order, method='vnpay', amount=Decimal(1), transaction_id='T2',
                                     pay_url='http://old', vnp_create_date='20260101000000')
        recalc_order(self.order)
        pay.refresh_from_db()
        self.assertEqual((pay.amount, pay.pay_url, pay.vnp_create_date), (Decimal(300000), '', ''))

    def test_recalc_keeps_vnpay_link_when_amount_unchanged(self):
        """Số tiền không đổi -> giữ nguyên link VNPay."""
        pay = Payment.objects.create(order=self.order, method='vnpay', amount=Decimal(300000), transaction_id='T3', pay_url='http://keep')
        recalc_order(self.order)
        pay.refresh_from_db()
        self.assertEqual(pay.pay_url, 'http://keep')

    def test_recalc_ignores_non_pending_payment(self):
        """Thanh toán đã thành công không bị đổi số tiền."""
        pay = Payment.objects.create(order=self.order, method='cash', amount=Decimal(5), transaction_id='T4', status='success')
        recalc_order(self.order)
        pay.refresh_from_db()
        self.assertEqual(pay.amount, Decimal(5))


class ReleaseTableTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(status='occupied')

    def test_table_without_open_orders_becomes_empty(self):
        """Không còn đơn mở -> bàn về 'empty', trả True."""
        self.assertTrue(release_table_if_idle(self.table))
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'empty')

    def test_custom_status_cleaning_after_payment(self):
        """Truyền status='cleaning' -> bàn chuyển sang đang dọn."""
        release_table_if_idle(self.table, Table.Status.CLEANING)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'cleaning')

    def test_pending_and_confirmed_orders_keep_table_occupied(self):
        """Còn đơn pending/confirmed -> giữ nguyên trạng thái, trả False."""
        for status in ('pending', 'confirmed'):
            order = Order.objects.create(table=self.table, status=status)
            self.assertFalse(release_table_if_idle(self.table))
            self.table.refresh_from_db()
            self.assertEqual(self.table.status, 'occupied')
            order.delete()

    def test_completed_and_cancelled_orders_do_not_hold_table(self):
        """Đơn completed/cancelled không giữ bàn."""
        Order.objects.create(table=self.table, status='completed')
        Order.objects.create(table=self.table, status='cancelled')
        self.assertTrue(release_table_if_idle(self.table))

    def test_other_tables_orders_are_ignored(self):
        """Đơn mở của bàn khác không ảnh hưởng."""
        Order.objects.create(table=Table.objects.create(), status='pending')
        self.assertTrue(release_table_if_idle(self.table))
