"""Unit test cho api/models.py."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import Category, MenuItem, Order, OrderItem, Payment, Review, StaffCall, Table, UserAccount


class TableModelTests(TestCase):
    def test_save_assigns_number_equal_to_pk(self):
        """Tạo bàn -> number = id (cả trong DB)."""
        t = Table.objects.create(area='A')
        self.assertEqual(t.number, str(t.pk))
        t.refresh_from_db()
        self.assertEqual(t.number, str(t.pk))

    def test_save_overrides_manual_number(self):
        """Gán number tuỳ ý vẫn bị ghi đè bằng id."""
        t = Table(number='ZZ', area='A')
        t.save()
        self.assertEqual(t.number, str(t.pk))

    def test_resave_keeps_number(self):
        """Lưu lại bàn không đổi number."""
        t = Table.objects.create()
        t.area = 'B'
        t.save()
        self.assertEqual(Table.objects.get(pk=t.pk).number, str(t.pk))

    def test_numbers_unique_across_tables(self):
        """Nhiều bàn có number khác nhau."""
        self.assertEqual(len({Table.objects.create().number for _ in range(5)}), 5)

    def test_defaults_and_str(self):
        """Mặc định: capacity 4, status empty; __str__ = 'Bàn <id>'."""
        t = Table.objects.create()
        self.assertEqual((t.capacity, t.status, str(t)), (4, 'empty', f'Bàn {t.pk}'))


class ReviewModelTests(TestCase):
    def setUp(self):
        item = MenuItem.objects.create(name='A', price=Decimal(1000))
        order = Order.objects.create(table=Table.objects.create(), status='completed')
        self.oi = OrderItem.objects.create(order=order, menu_item=item, unit_price=item.price, status='served')

    def test_rating_range_1_to_5_valid(self):
        """Rating 1..5 hợp lệ."""
        for r in range(1, 6):
            Review(order_item=self.oi, rating=r).full_clean()

    def test_rating_out_of_range_invalid(self):
        """Rating 0, 6, 100 bị từ chối bởi validator."""
        for r in (0, 6, 100):
            with self.assertRaises(ValidationError, msg=r):
                Review(order_item=self.oi, rating=r).full_clean()

    def test_one_review_per_order_item(self):
        """Mỗi dòng món chỉ 1 đánh giá (OneToOne)."""
        Review.objects.create(order_item=self.oi, rating=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(order_item=self.oi, rating=4)


class OtherModelTests(TestCase):
    def test_category_ordering_by_sort_order_then_name(self):
        """Danh mục sắp theo sort_order rồi tên."""
        Category.objects.create(name='B', sort_order=1)
        Category.objects.create(name='A', sort_order=1)
        Category.objects.create(name='Z', sort_order=0)
        self.assertEqual([c.name for c in Category.objects.all()], ['Z', 'A', 'B'])

    def test_order_defaults_and_str(self):
        """Đơn mới: pending, tổng 0; __str__ có id bàn."""
        t = Table.objects.create()
        o = Order.objects.create(table=t)
        self.assertEqual((o.status, o.total_amount), ('pending', 0))
        self.assertIn(str(t.pk), str(o))

    def test_payment_status_is_success_helper(self):
        """payment_status_is_success đúng với success/refunded, sai với failed/chưa có."""
        o = Order.objects.create(table=Table.objects.create())
        self.assertFalse(o.payment_status_is_success())
        p = Payment.objects.create(order=o, method='cash', amount=1, transaction_id='x')
        self.assertFalse(o.payment_status_is_success())
        for st, expected in (('success', True), ('refunded', True), ('failed', False)):
            p.status = st
            p.save()
            self.assertEqual(o.payment_status_is_success(), expected, st)

    def test_status_choices_cover_expected_values(self):
        """Tập trạng thái hợp lệ của Order/OrderItem/StaffCall/Table."""
        self.assertEqual(set(Order.Status.values), {'pending', 'confirmed', 'completed', 'cancelled'})
        self.assertEqual(set(OrderItem.Status.values), {'pending', 'cooking', 'done', 'served'})
        self.assertEqual(set(StaffCall.Status.values), {'pending', 'accepted', 'resolved'})
        self.assertEqual(set(Table.Status.values), {'empty', 'occupied', 'cleaning'})

    def test_invalid_status_rejected_by_full_clean(self):
        """Trạng thái ngoài choices bị full_clean từ chối."""
        t = Table.objects.create()
        t.status = 'broken'
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_user_role_default_waiter_and_staffcall_str(self):
        """User mới mặc định role PV; StaffCall.__str__ có trạng thái."""
        self.assertEqual(UserAccount.objects.create_user('u', password='x').role, 'PV')
        c = StaffCall.objects.create(table=Table.objects.create())
        self.assertIn('pending', str(c))
