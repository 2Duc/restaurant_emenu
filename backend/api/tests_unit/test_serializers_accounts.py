"""Unit test cho serializers: Promotion, Review, Staff, ChangePassword, Order/Payment."""
from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from .. import serializers as s
from ..models import MenuItem, Order, OrderItem, Payment, Promotion, Table, UserAccount


def valid(ser):
    ok = ser.is_valid()
    return ok


def errors(ser):
    ser.is_valid()
    return ser.errors


def ctx(user):
    return {'request': SimpleNamespace(user=user)}


class PromotionSerializerTests(TestCase):
    def data(self, **kw):
        now = timezone.now()
        return {'code': 'sale10', 'discount_type': 'percent', 'value': '10', 'start_date': now.isoformat(),
                'end_date': (now + timedelta(days=1)).isoformat(), **kw}

    def test_valid_and_code_uppercased(self):
        """Mã hợp lệ và được viết hoa."""
        ser = s.PromotionSerializer(data=self.data())
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertEqual(ser.validated_data['code'], 'SALE10')

    def test_code_charset(self):
        """Mã chứa khoảng trắng/ký tự lạ bị từ chối; '-' và '_' cho phép."""
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(code='A B'))))
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(code='A$'))))
        self.assertTrue(valid(s.PromotionSerializer(data=self.data(code='A-B_1'))))

    def test_end_must_be_after_start(self):
        """Ngày kết thúc <= bắt đầu -> lỗi."""
        now = timezone.now().isoformat()
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(start_date=now, end_date=now))))

    def test_value_must_be_positive_and_percent_max_100(self):
        """Giá trị <= 0 sai; percent 101 sai, 100 đúng; fixed 101 đúng."""
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(value='0'))))
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(value='-5'))))
        self.assertFalse(valid(s.PromotionSerializer(data=self.data(value='101'))))
        self.assertTrue(valid(s.PromotionSerializer(data=self.data(value='100'))))
        self.assertTrue(valid(s.PromotionSerializer(data=self.data(discount_type='fixed', value='101'))))

    def test_partial_update_uses_instance_values(self):
        """PATCH chỉ đổi value=150 trên mã percent hiện có -> vẫn bị chặn (>100)."""
        now = timezone.now()
        p = Promotion.objects.create(code='X', discount_type='percent', value=10, start_date=now, end_date=now + timedelta(days=1))
        self.assertFalse(valid(s.PromotionSerializer(p, data={'value': '150'}, partial=True)))


class ReviewSerializerTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create()
        self.item = MenuItem.objects.create(name='A', price=1000)

    def make_item(self, item_status, order_status):
        order = Order.objects.create(table=self.table, status=order_status)
        return OrderItem.objects.create(order=order, menu_item=self.item, unit_price=1000, status=item_status)

    def test_valid_review(self):
        """Món đã phục vụ trong đơn hoàn tất, 5 sao -> hợp lệ."""
        oi = self.make_item('served', 'completed')
        self.assertTrue(valid(s.ReviewSerializer(data={'order_item': oi.pk, 'rating': 5})))

    def test_not_served_or_not_completed_rejected(self):
        """Món chưa phục vụ hoặc đơn chưa hoàn tất -> lỗi order_item."""
        for it, od in (('cooking', 'completed'), ('served', 'pending')):
            oi = self.make_item(it, od)
            self.assertIn('order_item', errors(s.ReviewSerializer(data={'order_item': oi.pk, 'rating': 5})))

    def test_rating_bounds(self):
        """Rating 0 và 6 sai; 1 và 5 đúng."""
        oi = self.make_item('served', 'completed')
        for r, ok in ((0, False), (1, True), (5, True), (6, False)):
            self.assertEqual(valid(s.ReviewSerializer(data={'order_item': oi.pk, 'rating': r})), ok, r)


class StaffSerializerTests(TestCase):
    PW = 'Str0ng!Pass_91'

    def setUp(self):
        self.admin = UserAccount.objects.create_user('ad', password='x', role='AD')
        self.manager = UserAccount.objects.create_user('ql', password='x', role='QL')

    def data(self, **kw):
        return {'username': 'nv1', 'role': 'PV', 'password': self.PW, **kw}

    def test_manager_cannot_grant_admin_role(self):
        """QL tạo tài khoản role AD -> lỗi trường role."""
        self.assertIn('role', errors(s.StaffSerializer(data=self.data(role='AD'), context=ctx(self.manager))))

    def test_admin_can_grant_admin_role(self):
        """AD tạo được tài khoản AD."""
        ser = s.StaffSerializer(data=self.data(role='AD'), context=ctx(self.admin))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_superuser_counts_as_admin(self):
        """Superuser (role khác AD) cũng cấp được AD."""
        su = UserAccount.objects.create_superuser('root', password='x')
        self.assertTrue(valid(s.StaffSerializer(data=self.data(role='AD'), context=ctx(su))))

    def test_no_request_context_cannot_grant_admin(self):
        """Không có request trong context -> không được cấp AD."""
        self.assertIn('role', errors(s.StaffSerializer(data=self.data(role='AD'), context={})))

    def test_manager_cannot_edit_admin_account(self):
        """QL sửa tài khoản AD -> lỗi detail."""
        ser = s.StaffSerializer(self.admin, data={'first_name': 'x'}, partial=True, context=ctx(self.manager))
        self.assertIn('detail', errors(ser))

    def test_admin_can_edit_admin_account(self):
        """AD sửa tài khoản AD -> hợp lệ."""
        ser = s.StaffSerializer(self.admin, data={'first_name': 'x'}, partial=True, context=ctx(self.admin))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_new_account_requires_password(self):
        """Tạo mới không có mật khẩu -> lỗi password."""
        d = self.data()
        del d['password']
        self.assertIn('password', errors(s.StaffSerializer(data=d, context=ctx(self.admin))))

    def test_weak_password_rejected(self):
        """Mật khẩu yếu (quá ngắn / toàn số) bị validator Django chặn."""
        for pw in ('123', '12345678'):
            self.assertIn('password', errors(s.StaffSerializer(data=self.data(password=pw), context=ctx(self.admin))), pw)

    def test_create_hashes_password_and_sets_is_staff(self):
        """create: mật khẩu băm; is_staff True cho QL/AD, False cho PV/BEP."""
        for role, flag in (('QL', True), ('AD', True), ('PV', False), ('BEP', False)):
            ser = s.StaffSerializer(data=self.data(username=f'u_{role}', role=role), context=ctx(self.admin))
            self.assertTrue(ser.is_valid(), ser.errors)
            u = ser.save()
            self.assertEqual(u.is_staff, flag, role)
            self.assertNotEqual(u.password, self.PW)
            self.assertTrue(u.check_password(self.PW))

    def test_update_changes_password_and_role_flag(self):
        """update: đổi mật khẩu và is_staff theo role mới."""
        u = UserAccount.objects.create_user('w', password='old', role='PV')
        ser = s.StaffSerializer(u, data={'role': 'QL', 'password': 'Another!Pass_77'}, partial=True, context=ctx(self.admin))
        self.assertTrue(ser.is_valid(), ser.errors)
        u = ser.save()
        self.assertTrue(u.is_staff)
        self.assertTrue(u.check_password('Another!Pass_77'))

    def test_password_not_in_output(self):
        """password là write_only, không xuất ra."""
        self.assertNotIn('password', s.StaffSerializer(self.manager).data)


class ChangePasswordSerializerTests(TestCase):
    def test_weak_new_password_rejected(self):
        """Mật khẩu mới yếu bị chặn; mạnh thì qua."""
        u = UserAccount.objects.create_user('a', password='x')
        c = ctx(u)
        self.assertFalse(valid(s.ChangePasswordSerializer(data={'old_password': 'x', 'new_password': '123'}, context=c)))
        self.assertTrue(valid(s.ChangePasswordSerializer(data={'old_password': 'x', 'new_password': 'Tr0ub4dor&3xyz'}, context=c)))


class OrderAndPaymentSerializerTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(table=Table.objects.create())

    def test_order_payment_fields_none_without_payment(self):
        """Đơn chưa có thanh toán -> payment_id/status/method None."""
        d = s.OrderSerializer(self.order).data
        self.assertEqual((d['payment_id'], d['payment_status'], d['payment_method']), (None, None, None))

    def test_order_payment_fields_with_payment(self):
        """Đơn có thanh toán -> hiển thị trạng thái/phương thức."""
        p = Payment.objects.create(order=self.order, method='cash', amount=1, transaction_id='t')
        d = s.OrderSerializer(Order.objects.get(pk=self.order.pk)).data
        self.assertEqual((d['payment_id'], d['payment_status'], d['payment_method']), (p.id, 'pending', 'cash'))

    def test_qr_image_only_for_pending_vnpay_with_url(self):
        """qr_image chỉ có khi VNPay + pending + có pay_url."""
        p = Payment.objects.create(order=self.order, method='vnpay', amount=1, transaction_id='t', pay_url='http://x')
        self.assertTrue(s.PaymentSerializer(p).data['qr_image'].startswith('data:image/png'))
        p.status = 'success'
        self.assertIsNone(s.PaymentSerializer(p).data['qr_image'])
        p.status, p.pay_url = 'pending', ''
        self.assertIsNone(s.PaymentSerializer(p).data['qr_image'])
        p.method, p.pay_url = 'cash', 'http://x'
        self.assertIsNone(s.PaymentSerializer(p).data['qr_image'])
