from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, Category, MenuItem, Order, OrderItem, Payment, StaffCall, SystemSetting, Table, UserAccount
from .services.system_settings import mask
from .services.table_token import make_table_token
from .services.vietqr import build_vietqr_payload, crc16_ccitt, verify_crc


def user_client(username, role):
    c = APIClient()
    c.force_authenticate(UserAccount.objects.create_user(username, password='x', role=role))
    return c


class VietQRTests(APITestCase):
    def test_crc16_known_vector(self):
        self.assertEqual(crc16_ccitt('123456789'), '29B1')   # CRC-16/CCITT-FALSE chuẩn

    def test_payload_structure_and_crc(self):
        p = build_vietqr_payload('970436', '0011001234567', 170000, 'DON12')
        self.assertTrue(p.startswith('000201010212'))
        self.assertIn('0010A000000727', p)
        self.assertIn('QRIBFTTA', p)
        self.assertIn('5303704', p)
        self.assertIn('0613'.replace('0613', '540') + '6170000', p)   # tag 54 độ dài 6
        self.assertIn('5802VN', p)
        self.assertIn('0805DON12', p)
        self.assertEqual(p[-8:-4], '6304')
        self.assertTrue(verify_crc(p))
        self.assertFalse(verify_crc(p[:-1] + ('0' if p[-1] != '0' else '1')))

    def test_content_stripped_to_ascii(self):
        p = build_vietqr_payload('970436', '123456789', 1000, 'Đơn #5!')
        self.assertIn('Don 5', p)
        self.assertTrue(verify_crc(p))


class SystemSettingModelTests(APITestCase):
    def test_singleton(self):
        a = SystemSetting.load()
        b = SystemSetting.objects.create(cash_enabled=False)
        self.assertEqual((a.pk, b.pk), (1, 1))
        self.assertEqual(SystemSetting.objects.count(), 1)

    def test_bank_configured_and_mask(self):
        s = SystemSetting.load()
        self.assertFalse(s.bank_configured)
        s.bank_bin, s.bank_account_no, s.bank_account_name = '970436', '123456', 'A'
        self.assertTrue(s.bank_configured)
        self.assertEqual(mask('CAG0U1JV'), 'CA****JV')
        self.assertEqual(mask(''), '')


class SettingsApiTests(APITestCase):
    def test_public_get_hides_bank_until_configured(self):
        r = self.client.get('/api/settings/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['methods'], {'cash': True, 'bank_transfer': False, 'vnpay': True})
        self.assertIsNone(r.data['bank'])
        self.assertNotIn('config', r.data)
        self.assertNotIn('gateway', r.data)

    def test_patch_only_admin(self):
        body = {'bank_bin': '970436', 'bank_name': 'Vietcombank', 'bank_account_no': '0011001234567', 'bank_account_name': 'abc restaurant'}
        self.assertEqual(self.client.patch('/api/settings/', body, format='json').status_code, 401)
        for role in ('PV', 'BEP', 'QL'):
            self.assertEqual(user_client(role.lower(), role).patch('/api/settings/', body, format='json').status_code, 403)
        r = user_client('ad', 'AD').patch('/api/settings/', body, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['config']['bank_account_name'], 'ABC RESTAURANT')
        self.assertTrue(r.data['methods']['bank_transfer'])
        self.assertEqual(AuditLog.objects.filter(action='SYSTEM_SETTING_UPDATE').count(), 1)
        pub = self.client.get('/api/settings/').data
        self.assertEqual(pub['bank']['account_no'], '0011001234567')

    @override_settings(PAYMENT_GATEWAY_MODE='vnpay', VNPAY_TMN_CODE='CAG0U1JV', VNPAY_HASH_SECRET_KEY='supersecret')
    def test_admin_get_has_masked_gateway_no_secret(self):
        r = user_client('ad', 'AD').get('/api/settings/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['gateway'], {'mode': 'vnpay', 'tmn_code': 'CA****JV', 'has_hash_secret': True})
        self.assertNotIn('supersecret', str(r.data))
        self.assertEqual(user_client('ql', 'QL').get('/api/settings/').data.get('gateway'), None)

    def test_validation(self):
        ad = user_client('ad', 'AD')
        self.assertEqual(ad.patch('/api/settings/', {'bank_bin': '12'}, format='json').status_code, 400)
        self.assertEqual(ad.patch('/api/settings/', {'bank_account_no': 'abc123'}, format='json').status_code, 400)
        self.assertEqual(ad.patch('/api/settings/', {'staff_call_cooldown_minutes': 0}, format='json').status_code, 400)
        self.assertEqual(ad.patch('/api/settings/', {'staff_call_cooldown_minutes': 99}, format='json').status_code, 400)
        self.assertEqual(ad.patch('/api/settings/', {'bank_bin': '970436'}, format='json').status_code, 400)   # thiếu STK/chủ TK


class BankTransferFlowTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        cat = Category.objects.create(name='Chính')
        dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))
        self.order = Order.objects.create(table=self.table, status='pending', subtotal_amount=170000, total_amount=170000)
        OrderItem.objects.create(order=self.order, menu_item=dish, quantity=2, unit_price=dish.price)
        SystemSetting.objects.update_or_create(pk=1, defaults=dict(
            bank_bin='970436', bank_name='Vietcombank', bank_account_no='0011001234567', bank_account_name='ABC RESTAURANT'))

    def _create(self, method='bank_transfer'):
        return self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': method}, format='json')

    def test_create_returns_bank_info_qr_and_staff_call(self):
        r = self._create()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['method'], 'bank_transfer')
        self.assertEqual(r.data['status'], 'pending')
        self.assertTrue(r.data['qr_image'].startswith('data:image/png;base64,'))
        self.assertEqual(r.data['bank_info'], {'bank_name': 'Vietcombank', 'account_no': '0011001234567',
                                               'account_name': 'ABC RESTAURANT', 'content': f'DON{self.order.id}', 'amount': 170000})
        self._create()
        calls = StaffCall.objects.filter(table=self.table, status='pending')
        self.assertEqual(calls.count(), 1)
        self.assertTrue(calls.first().message.startswith('Khách chờ xác nhận chuyển khoản'))

    def test_staff_confirm_manual_completes_order_and_audit(self):
        pay = self._create().data
        # khách và bếp không xác nhận được
        self.assertIn(self.client.post(f"/api/payments/{pay['id']}/confirm-manual/").status_code, (401, 403))
        self.assertEqual(user_client('chef', 'BEP').post(f"/api/payments/{pay['id']}/confirm-manual/").status_code, 403)
        for i, role in enumerate(('PV', 'QL', 'AD')):
            if i:
                Payment.objects.filter(pk=pay['id']).update(status='pending', paid_at=None)
                Order.objects.filter(pk=self.order.pk).update(status='pending')
                Table.objects.filter(pk=self.table.pk).update(status='occupied')
            r = user_client(f'u{i}', role).post(f"/api/payments/{pay['id']}/confirm-manual/")
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['status'], 'success')
            self.assertIsNone(r.data['qr_image'])
            self.order.refresh_from_db(); self.table.refresh_from_db()
            self.assertEqual(self.order.status, 'completed')
            self.assertEqual(self.table.status, 'cleaning')
        self.assertEqual(StaffCall.objects.get(table=self.table).status, 'resolved')
        self.assertTrue(AuditLog.objects.filter(action='PAYMENT_BANK_CONFIRM').exists())

    def test_confirm_manual_also_handles_cash_and_rejects_vnpay(self):
        pay = self._create('cash').data
        pv = user_client('pv', 'PV')
        self.assertEqual(pv.post(f"/api/payments/{pay['id']}/confirm-manual/").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='PAYMENT_CASH_CONFIRM').exists())
        Payment.objects.filter(pk=pay['id']).update(method='vnpay', status='pending')
        self.assertEqual(pv.post(f"/api/payments/{pay['id']}/confirm-manual/").status_code, 400)

    def test_confirm_cash_endpoint_still_cash_only(self):
        pay = self._create().data
        self.assertEqual(user_client('pv', 'PV').post(f"/api/payments/{pay['id']}/confirm-cash/").status_code, 400)

    def test_amount_changed_requires_new_request(self):
        pay = self._create().data
        Order.objects.filter(pk=self.order.pk).update(total_amount=200000)
        self.assertEqual(user_client('pv', 'PV').post(f"/api/payments/{pay['id']}/confirm-manual/").status_code, 400)

    def test_report_includes_bank_transfer(self):
        pay = self._create().data
        user_client('pv', 'PV').post(f"/api/payments/{pay['id']}/confirm-manual/")
        r = user_client('ql', 'QL').get('/api/reports/summary/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('bank_transfer', [m['method'] for m in r.data['methods']])

    def test_disabled_or_unconfigured_method_returns_400(self):
        SystemSetting.objects.filter(pk=1).update(cash_enabled=False)
        self.assertEqual(self._create('cash').status_code, 400)
        SystemSetting.objects.filter(pk=1).update(vnpay_enabled=False)
        self.assertEqual(self._create('vnpay').status_code, 400)
        SystemSetting.objects.filter(pk=1).update(bank_transfer_enabled=False)
        self.assertEqual(self._create().status_code, 400)
        SystemSetting.objects.filter(pk=1).update(bank_transfer_enabled=True, bank_account_no='')
        self.assertEqual(self._create().status_code, 400)   # chưa cấu hình TK
        self.assertFalse(Payment.objects.exists())

    def test_staff_call_cooldown_uses_setting(self):
        from datetime import timedelta
        from django.utils import timezone
        old = StaffCall.objects.create(table=self.table, message='x')
        StaffCall.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        r = self.client.post('/api/staff-calls/', {'table': self.table.id, 'message': 'y'}, format='json')
        self.assertEqual(r.status_code, 201)   # 5 phút > 2 phút mặc định
        StaffCall.objects.all().delete()
        old = StaffCall.objects.create(table=self.table, message='x')
        StaffCall.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        SystemSetting.objects.filter(pk=1).update(staff_call_cooldown_minutes=10)
        r = self.client.post('/api/staff-calls/', {'table': self.table.id, 'message': 'y'}, format='json')
        self.assertEqual(r.status_code, 200)   # dùng lại yêu cầu cũ
