from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from unittest import mock
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Category, MenuItem, Order, OrderItem, Payment, StaffCall, Table, UserAccount
from .services import vnpay_services as vnpay
from .services.table_token import make_table_token
from .tests import VNPAY_SETTINGS, signed_return_params


def make_order(table, total=170000):
    cat = Category.objects.create(name='C')
    dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))
    order = Order.objects.create(table=table, status='pending', subtotal_amount=total, total_amount=total)
    OrderItem.objects.create(order=order, menu_item=dish, quantity=2, unit_price=dish.price)
    return order


class CashFlowTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A', status='occupied')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        self.order = make_order(self.table)

    def _cash(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'cash'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_customer_cash_creates_single_staff_call_and_staff_roles_confirm(self):
        for i, role in enumerate(('PV', 'QL', 'AD')):
            Payment.objects.all().delete(); StaffCall.objects.all().delete()
            Order.objects.filter(pk=self.order.pk).update(status='pending')
            Table.objects.filter(pk=self.table.pk).update(status='occupied')
            pay = self._cash()
            self._cash()   # tạo lại không nhân đôi staff call
            calls = StaffCall.objects.filter(table=self.table, status='pending')
            self.assertEqual(calls.count(), 1)
            self.assertTrue(calls.first().message.startswith('Thanh toán tiền mặt'))
            api = APIClient(); api.force_authenticate(UserAccount.objects.create_user(f'u{i}', password='x', role=role))
            r = api.post(f"/api/payments/{pay['id']}/confirm-cash/")
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['status'], 'success')
            self.order.refresh_from_db(); self.table.refresh_from_db()
            self.assertEqual(self.order.status, 'completed')
            self.assertEqual(self.table.status, 'cleaning')
            self.assertEqual(StaffCall.objects.get(table=self.table).status, 'resolved')
            # xác nhận lần 2 idempotent
            self.assertEqual(api.post(f"/api/payments/{pay['id']}/confirm-cash/").status_code, 200)

    def test_kitchen_and_anonymous_cannot_confirm(self):
        pay = self._cash()
        self.assertIn(self.client.post(f"/api/payments/{pay['id']}/confirm-cash/").status_code, (401, 403))
        chef = APIClient(); chef.force_authenticate(UserAccount.objects.create_user('chef', password='x', role='BEP'))
        self.assertEqual(chef.post(f"/api/payments/{pay['id']}/confirm-cash/").status_code, 403)
        self.assertEqual(Payment.objects.get(pk=pay['id']).status, 'pending')

    def test_table_not_released_when_other_open_order(self):
        pay = self._cash()
        Order.objects.create(table=self.table, status='pending', subtotal_amount=1000, total_amount=1000)
        api = APIClient(); api.force_authenticate(UserAccount.objects.create_user('pv', password='x', role='PV'))
        api.post(f"/api/payments/{pay['id']}/confirm-cash/")
        self.table.refresh_from_db(); self.assertEqual(self.table.status, 'occupied')


@override_settings(**VNPAY_SETTINGS)
class VNPayExtraTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        self.order = make_order(self.table)
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.payment = Payment.objects.get(pk=r.data['id'])
        self.url = r.data['pay_url']

    def test_url_params(self):
        qs = {k: v[0] for k, v in parse_qs(urlparse(self.url).query).items()}
        self.assertEqual(qs['vnp_Amount'], '17000000')
        self.assertEqual(qs['vnp_TmnCode'], 'TESTCODE')
        self.assertEqual(qs['vnp_TxnRef'], self.payment.transaction_id)
        self.assertEqual(qs['vnp_CurrCode'], 'VND')
        self.assertEqual(qs['vnp_Command'], 'pay')
        self.assertTrue(vnpay.verify_vnpay_response(qs))
        qs['vnp_Amount'] = '1'
        self.assertFalse(vnpay.verify_vnpay_response(qs))

    def test_ipn_bad_signature_rejected(self):
        p = signed_return_params(self.payment); p['vnp_SecureHash'] = 'deadbeef'
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', p).data['RspCode'], '97')
        p = signed_return_params(self.payment); p['vnp_ResponseCode'] = '24'   # đổi tham số sau khi ký
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', p).data['RspCode'], '97')
        self.payment.refresh_from_db(); self.assertEqual(self.payment.status, 'pending')

    def test_ipn_amount_mismatch_and_unknown_txn(self):
        r = self.client.get('/api/payments/vnpay-ipn/', signed_return_params(self.payment, amount=100))
        self.assertEqual(r.data['RspCode'], '04')
        ghost = signed_return_params(self.payment); ghost['vnp_TxnRef'] = 'nope'
        ghost['vnp_SecureHash'] = vnpay.hmacsha512('TESTSECRET', vnpay._encoded_pairs({k: v for k, v in ghost.items() if k != 'vnp_SecureHash'}))
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', ghost).data['RspCode'], '01')
        self.payment.refresh_from_db(); self.assertEqual(self.payment.status, 'pending')

    def test_ipn_success_then_return_is_idempotent(self):
        p = signed_return_params(self.payment)
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', p).data['RspCode'], '00')
        self.payment.refresh_from_db(); first = self.payment.paid_at
        self.assertEqual(self.payment.status, 'success')
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', p).data['RspCode'], '02')
        self.assertIn('status=success', self.client.get('/api/payments/vnpay-return/', p)['Location'])
        self.payment.refresh_from_db(); self.assertEqual(self.payment.paid_at, first)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    def test_wrong_terminal_rejected(self):
        p = signed_return_params(self.payment); p['vnp_TmnCode'] = 'OTHER'
        p['vnp_SecureHash'] = vnpay.hmacsha512('TESTSECRET', vnpay._encoded_pairs({k: v for k, v in p.items() if k != 'vnp_SecureHash'}))
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', p).data['RspCode'], '99')
        self.assertIn('status=invalid', self.client.get('/api/payments/vnpay-return/', p)['Location'])


class WsAuthTests(TransactionTestCase):
    def setUp(self):
        from backend.asgi import application
        self.app = application
        self.table = Table.objects.create(area='A')
        mk = UserAccount.objects.create_user
        self.users = {r: mk(r.lower(), password='x', role=r) for r in ('PV', 'BEP', 'QL', 'AD')}

    def _sock(self, group, token=None):
        return WebsocketCommunicator(self.app, f'/ws/{group}/' + (f'?token={token}' if token else ''))

    async def _ok(self, group, token):
        c = self._sock(group, token); ok, _ = await c.connect()
        if ok: await c.disconnect()
        return ok

    def test_group_access_matrix(self):
        async_to_sync(self._matrix)()

    async def _matrix(self):
        tok = {r: str(AccessToken.for_user(u)) for r, u in self.users.items()}
        # không token / token rác bị từ chối
        for g in ('kitchen_orders', 'staff_orders'):
            self.assertFalse(await self._ok(g, None))
            self.assertFalse(await self._ok(g, 'garbage'))
        self.assertTrue(await self._ok('kitchen_orders', tok['BEP']))
        self.assertTrue(await self._ok('kitchen_orders', tok['QL']))
        self.assertTrue(await self._ok('kitchen_orders', tok['AD']))
        self.assertFalse(await self._ok('kitchen_orders', tok['PV']))
        self.assertTrue(await self._ok('staff_orders', tok['PV']))
        self.assertTrue(await self._ok('staff_orders', tok['QL']))
        self.assertTrue(await self._ok('staff_orders', tok['AD']))
        self.assertFalse(await self._ok('staff_orders', tok['BEP']))
        # WS-02: kênh bàn cần token phiên bàn đúng bàn (hoặc JWT nhân viên)
        other = await sync_to_async(Table.objects.create)(area='B')
        ttok = make_table_token(self.table)
        self.assertTrue(await self._ok(f'table_{self.table.id}', ttok))
        self.assertFalse(await self._ok(f'table_{self.table.id}', None))
        self.assertFalse(await self._ok(f'table_{self.table.id}', 'garbage'))
        self.assertFalse(await self._ok(f'table_{other.id}', ttok))          # token bàn khác
        for r in ('PV', 'BEP', 'QL', 'AD'):
            self.assertTrue(await self._ok(f'table_{self.table.id}', tok[r]))   # nhân viên vào được
        await sync_to_async(Table.objects.filter(pk=self.table.pk).update)(qr_token='rotated-secret')
        self.assertFalse(await self._ok(f'table_{self.table.id}', ttok))     # QR đã đổi mã -> token cũ chết

    def test_broadcasts_reach_groups(self):
        async_to_sync(self._broadcast)()

    async def _broadcast(self):
        tok = str(AccessToken.for_user(self.users['QL']))
        kitchen, staff = self._sock('kitchen_orders', tok), self._sock('staff_orders', tok)
        for c in (kitchen, staff):
            self.assertTrue((await c.connect())[0])
        layer = get_channel_layer()
        await layer.group_send('staff_orders', {'type': 'staff_call', 'call': {'id': 1}})
        self.assertEqual((await staff.receive_json_from(timeout=3))['type'], 'staff_call')
        await layer.group_send('kitchen_orders', {'type': 'new_order', 'order': {'id': 1}})
        self.assertEqual((await kitchen.receive_json_from(timeout=3))['type'], 'new_order')
        await layer.group_send('kitchen_orders', {'type': 'item_status_updated', 'order_item': {'id': 1}})
        self.assertEqual((await kitchen.receive_json_from(timeout=3))['type'], 'item_status_updated')
        await kitchen.send_json_to({'type': 'ping'})
        self.assertEqual((await kitchen.receive_json_from(timeout=3))['type'], 'pong')
        for c in (kitchen, staff):
            await c.disconnect()


class CleaningTableOrderTests(APITestCase):
    def test_customer_cannot_order_on_cleaning_table(self):
        table = Table.objects.create(area='A', status='cleaning')
        dish = MenuItem.objects.create(category=Category.objects.create(name='C'), name='Phở', price=Decimal('85000'))
        body = {'table_id': table.id, 'items': [{'menu_item_id': dish.id, 'quantity': 1}]}
        r = self.client.post('/api/orders/', body, format='json', HTTP_X_TABLE_TOKEN=make_table_token(table))
        self.assertEqual(r.status_code, 400)
        self.assertIn('Bàn đang được dọn', r.data['detail'])
        self.assertEqual(Order.objects.count(), 0)
        api = APIClient(); api.force_authenticate(UserAccount.objects.create_user('pv', password='x', role='PV'))
        self.assertEqual(api.post('/api/orders/', body, format='json').status_code, 201)


class KitchenApiTests(APITestCase):
    def test_availability_rejects_garbage_values(self):
        dish = MenuItem.objects.create(category=Category.objects.create(name='C'), name='Phở', price=Decimal('85000'))
        chef = APIClient(); chef.force_authenticate(UserAccount.objects.create_user('chef2', password='x', role='BEP'))
        url = f'/api/menu-items/{dish.id}/availability/'
        for bad in ('abc', '', 2, None, [True]):
            r = chef.post(url, {'is_available': bad}, format='json')
            self.assertEqual(r.status_code, 400, bad)
            self.assertEqual(r.data['detail'], 'is_available phải là true/false.')
            dish.refresh_from_db(); self.assertTrue(dish.is_available)
        self.assertEqual(chef.post(url, {'is_available': 'OFF'}, format='json').status_code, 200)
        dish.refresh_from_db(); self.assertFalse(dish.is_available)
        self.assertEqual(chef.post(url, {'is_available': 'Yes'}, format='json').status_code, 200)
        dish.refresh_from_db(); self.assertTrue(dish.is_available)


class MockGatewayTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A', status='occupied')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        self.order = make_order(self.table)

    def _create(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    @override_settings(PAYMENT_GATEWAY_MODE='mock', FRONTEND_BASE_URL='http://localhost:5173')
    def test_mock_success_cancel_idempotent(self):
        data = self._create()
        qs = parse_qs(urlparse(data['pay_url']).query)
        self.assertTrue(data['pay_url'].startswith('http://localhost:5173/payment/mock?'))
        self.assertEqual(qs['amount'], ['170000'])
        self.assertTrue(data['qr_image'].startswith('data:image/png;base64,'))
        txn = qs['txn'][0]
        r = self.client.post('/api/payments/mock-callback/', {'txn_ref': txn, 'result': 'success'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'success')
        self.order.refresh_from_db(); self.table.refresh_from_db()
        self.assertEqual(self.order.status, 'completed'); self.assertEqual(self.table.status, 'cleaning')
        r2 = self.client.post('/api/payments/mock-callback/', {'txn_ref': txn, 'result': 'cancel'}, format='json')
        self.assertEqual(r2.data['status'], 'success'); self.assertFalse(r2.data['applied'])
        self.assertEqual(Payment.objects.get(transaction_id=txn).status, 'success')

    @override_settings(PAYMENT_GATEWAY_MODE='mock')
    def test_mock_cancel_marks_failed(self):
        txn = parse_qs(urlparse(self._create()['pay_url']).query)['txn'][0]
        r = self.client.post('/api/payments/mock-callback/', {'txn_ref': txn, 'result': 'cancel'}, format='json')
        self.assertEqual(r.data['status'], 'failed')
        self.order.refresh_from_db(); self.assertEqual(self.order.status, 'pending')
        self.assertEqual(self.client.post('/api/payments/mock-callback/', {'txn_ref': txn, 'result': 'x'}, format='json').status_code, 400)

    @override_settings(**VNPAY_SETTINGS)
    def test_mock_endpoint_404_in_vnpay_mode(self):
        r = self.client.post('/api/payments/mock-callback/', {'txn_ref': 'x', 'result': 'success'}, format='json')
        self.assertEqual(r.status_code, 404)


@override_settings(**VNPAY_SETTINGS)
class MerchantApiErrorTests(APITestCase):
    def test_sync_oserror_is_controlled(self):
        table = Table.objects.create(area='A', status='occupied')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(table)
        order = make_order(table)
        pay = self.client.post('/api/payments/create/', {'order_id': order.id, 'method': 'vnpay'}, format='json').data
        with mock.patch('api.services.vnpay_services.requests.post', side_effect=OSError('bad ca bundle')):
            r = self.client.post(f"/api/payments/{pay['id']}/sync/", {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'pending')
        self.assertIn('VNPay', r.data['sync_error'])
        with mock.patch('api.services.vnpay_services.requests.post', side_effect=OSError('x')):
            with self.assertRaises(vnpay.VNPayError):
                vnpay.query_transaction(txn_ref='a', transaction_date='20260101000000', order_info='x')
