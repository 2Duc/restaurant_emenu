from datetime import timedelta
from decimal import Decimal
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, MenuItem, Order, OrderItem, Payment, Promotion, StaffCall, Table, UserAccount
from .services import vnpay_services as vnpay
from .services.table_token import make_table_token

VNPAY_SETTINGS = dict(
    PAYMENT_GATEWAY_MODE='vnpay', VNPAY_TMN_CODE='TESTCODE', VNPAY_HASH_SECRET_KEY='TESTSECRET',
    VNPAY_RETURN_URL='http://127.0.0.1:8000/api/payments/vnpay-return/',
    FRONTEND_RETURN_URL='http://localhost:5173/payment-result',
    FRONTEND_BASE_URL='http://localhost:5173',
)


def signed_return_params(payment, *, response_code='00', status='00', amount=None):
    params = {
        'vnp_TmnCode': 'TESTCODE', 'vnp_TxnRef': payment.transaction_id,
        'vnp_Amount': str(amount if amount is not None else int(payment.amount) * 100),
        'vnp_ResponseCode': response_code, 'vnp_TransactionStatus': status,
        'vnp_TransactionNo': '14000001', 'vnp_BankCode': 'NCB', 'vnp_PayDate': '20261117101500',
        'vnp_OrderInfo': 'test',
    }
    params['vnp_SecureHash'] = vnpay.hmacsha512('TESTSECRET', vnpay._encoded_pairs(params))
    return params


@override_settings(**VNPAY_SETTINGS)
class PaymentFlowTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)   # khách đang ngồi bàn này (BR-02)
        cat = Category.objects.create(name='Chính')
        dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))
        self.order = Order.objects.create(table=self.table, status='pending', subtotal_amount=170000, total_amount=170000)
        OrderItem.objects.create(order=self.order, menu_item=dish, quantity=2, unit_price=dish.price)

    def test_table_number_is_id(self):
        self.assertEqual(self.table.number, str(self.table.id))

    def test_vnpay_create_returns_url_and_qr(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['pay_url'].startswith('https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?'))
        self.assertTrue(r.data['qr_image'].startswith('data:image/png;base64,'))
        qs = parse_qs(urlparse(r.data['pay_url']).query)
        self.assertEqual(qs['vnp_Amount'], ['17000000'])
        # chữ ký của chính URL phải hợp lệ
        self.assertTrue(vnpay.verify_vnpay_response({k: v[0] for k, v in qs.items()}))
        # gọi lại trong vài phút → dùng lại cùng link, không sinh txn mới
        again = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.assertEqual(again.data['transaction_id'], r.data['transaction_id'])

    def test_return_url_success_completes_order(self):
        self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        payment = Payment.objects.get(order=self.order)
        r = self.client.get('/api/payments/vnpay-return/', signed_return_params(payment))
        self.assertEqual(r.status_code, 302)
        self.assertIn('status=success', r['Location'])
        self.assertIn(f'table={self.table.id}', r['Location'])
        payment.refresh_from_db(); self.order.refresh_from_db(); self.table.refresh_from_db()
        self.assertEqual(payment.status, 'success')
        self.assertEqual(payment.vnp_transaction_no, '14000001')
        self.assertEqual(self.order.status, 'completed')
        self.assertEqual(self.table.status, 'cleaning')

    def test_result_page_can_verify_payment_from_backend(self):
        # Trang /payment-result hỏi lại backend thay vì tin tham số URL: đơn chưa trả → payment_status không phải success
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.assertEqual(self.client.get(f'/api/orders/{self.order.id}/').data['payment_status'], 'pending')
        payment = Payment.objects.get(pk=r.data['id'])
        self.client.get('/api/payments/vnpay-return/', signed_return_params(payment))
        shown = self.client.get(f'/api/orders/{self.order.id}/').data
        self.assertEqual((shown['payment_status'], shown['payment_method']), ('success', 'vnpay'))
        self.assertEqual(self.client.get(f'/api/orders/{self.order.id}/', HTTP_X_TABLE_TOKEN='garbage').status_code, 403)

    def test_return_url_rejects_bad_signature_and_wrong_amount(self):
        self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        payment = Payment.objects.get(order=self.order)
        bad = signed_return_params(payment); bad['vnp_Amount'] = '100'
        self.assertIn('status=invalid', self.client.get('/api/payments/vnpay-return/', bad)['Location'])
        wrong_amount = signed_return_params(payment, amount=100)
        self.assertIn('status=invalid', self.client.get('/api/payments/vnpay-return/', wrong_amount)['Location'])
        payment.refresh_from_db(); self.assertEqual(payment.status, 'pending')

    def test_ipn_confirms_and_is_idempotent(self):
        self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        payment = Payment.objects.get(order=self.order)
        params = signed_return_params(payment)
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', params).data['RspCode'], '00')
        self.assertEqual(self.client.get('/api/payments/vnpay-ipn/', params).data['RspCode'], '02')

    def test_failed_payment_keeps_order_open(self):
        self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        payment = Payment.objects.get(order=self.order)
        r = self.client.get('/api/payments/vnpay-return/', signed_return_params(payment, response_code='24', status='02'))
        self.assertIn('status=failed', r['Location'])
        self.order.refresh_from_db(); self.assertEqual(self.order.status, 'pending')

    def test_cash_requires_confirm_button(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'cash'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['status'], 'pending')
        self.assertIsNone(r.data['qr_image'])
        self.order.refresh_from_db(); self.assertEqual(self.order.status, 'pending')
        self.assertIn(self.client.post(f"/api/payments/{r.data['id']}/confirm-cash/").status_code, (401, 403))   # khách không tự xác nhận
        self.assertEqual(StaffCall.objects.filter(table=self.table, status='pending').count(), 1)          # nhân viên được báo
        self.client.force_authenticate(UserAccount.objects.create_user('pv', password='x', role='PV'))
        done = self.client.post(f"/api/payments/{r.data['id']}/confirm-cash/")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(StaffCall.objects.filter(table=self.table, status='pending').count(), 0)
        self.assertEqual(done.data['status'], 'success')
        self.order.refresh_from_db(); self.assertEqual(self.order.status, 'completed')

    def test_confirm_cash_rejects_vnpay_payment(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.client.force_authenticate(UserAccount.objects.create_user('pv', password='x', role='PV'))
        self.assertEqual(self.client.post(f"/api/payments/{r.data['id']}/confirm-cash/").status_code, 400)

    def test_switching_from_cash_to_transfer_creates_new_link(self):
        cash = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'cash'}, format='json')
        vn = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        self.assertEqual(cash.data['id'], vn.data['id'])
        self.assertEqual(vn.data['method'], 'vnpay')
        self.assertTrue(vn.data['pay_url'])

    def test_sync_marks_paid_when_vnpay_says_success(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        fake = {'vnp_ResponseCode': '00', 'vnp_TransactionStatus': '00', 'vnp_TmnCode': 'TESTCODE',
                'vnp_Amount': '17000000', 'vnp_TransactionNo': '999', 'vnp_BankCode': 'NCB', 'vnp_PayDate': '20261117101500'}
        with mock.patch('api.views.payment_view.query_transaction', return_value=fake):
            out = self.client.post(f"/api/payments/{r.data['id']}/sync/")
        self.assertEqual(out.data['status'], 'success')
        self.assertEqual(out.data['vnp_transaction_no'], '999')

    def test_sync_survives_vnpay_outage(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        with mock.patch('api.views.payment_view.query_transaction', side_effect=vnpay.VNPayError('boom')):
            out = self.client.post(f"/api/payments/{r.data['id']}/sync/")
        self.assertEqual(out.status_code, 200)
        self.assertEqual(out.data['status'], 'pending')
        self.assertIn('boom', out.data['sync_error'])

    def test_query_and_refund_are_manager_only_and_refund_works(self):
        r = self.client.post('/api/payments/create/', {'order_id': self.order.id, 'method': 'vnpay'}, format='json')
        payment = Payment.objects.get(pk=r.data['id'])
        self.client.get('/api/payments/vnpay-return/', signed_return_params(payment))
        self.assertIn(self.client.post('/api/payments/refund/', {'payment_id': payment.id}, format='json').status_code, (401, 403))
        manager = UserAccount.objects.create_user('mgr', password='x', role='QL')
        self.client.force_authenticate(manager)
        with mock.patch('api.views.payment_view.refund_transaction', return_value={'vnp_ResponseCode': '00'}) as m:
            out = self.client.post('/api/payments/refund/', {'payment_id': payment.id, 'amount': 70000}, format='json')
            self.assertEqual(out.status_code, 200, out.data)
            self.assertFalse(m.call_args.kwargs['full_refund'])
            out = self.client.post('/api/payments/refund/', {'payment_id': payment.id}, format='json')
        payment.refresh_from_db()
        self.assertEqual(int(payment.refunded_amount), 170000)
        self.assertEqual(payment.status, 'refunded')
        with mock.patch('api.views.payment_view.query_transaction', return_value={'vnp_ResponseCode': '00'}):
            q = self.client.post('/api/payments/query/', {'order_id': self.order.id}, format='json')
        self.assertEqual(q.status_code, 200)
        self.assertEqual(q.data['vnpay']['vnp_ResponseCode'], '00')


@override_settings(**VNPAY_SETTINGS)
class TableQrTests(APITestCase):
    def test_qr_contains_link_with_table_id(self):
        table = Table.objects.create(area='A')
        self.assertIn(self.client.get(f'/api/tables/{table.id}/qr/').status_code, (401, 403))
        self.client.force_authenticate(UserAccount.objects.create_user('w', password='x', role='PV'))
        r = self.client.get(f'/api/tables/{table.id}/qr/')
        self.assertEqual(r.data['url'], f'http://localhost:5173/table/{table.id}?k={table.qr_token}')
        self.assertTrue(r.data['qr_image'].startswith('data:image/png;base64,'))
        table.refresh_from_db(); self.assertEqual(table.qr_code_url, f'http://localhost:5173/table/{table.id}')   # DB/API công khai không chứa mã k
        lan = self.client.get(f'/api/tables/{table.id}/qr/', {'base_url': 'http://192.168.1.5:5173/'})
        self.assertEqual(lan.data['url'], f'http://192.168.1.5:5173/table/{table.id}?k={table.qr_token}')
        evil = self.client.get(f'/api/tables/{table.id}/qr/', {'base_url': 'javascript:alert(1)'})
        self.assertEqual(evil.data['url'], f'http://localhost:5173/table/{table.id}?k={table.qr_token}')
        self.assertEqual(len(self.client.get('/api/tables/qr-codes/').data), 1)

    def test_customer_can_open_table_by_id(self):
        table = Table.objects.create(area='A')
        self.assertEqual(self.client.get(f'/api/tables/{table.id}/').data['id'], table.id)


@override_settings(**VNPAY_SETTINGS, VNPAY_PAYMENT_URL='https://sandbox.vnpayment.vn/paymentv2/vpcpay.html')
class VNPaySignatureTests(APITestCase):
    def test_build_url_contains_signed_amount(self):
        url, create_date = vnpay.build_vnpay_payment_url(amount=100000, order_info='Test', txn_ref='ABC123')
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params['vnp_Amount'][0], '10000000')
        self.assertEqual(params['vnp_TxnRef'][0], 'ABC123')
        self.assertEqual(params['vnp_CreateDate'][0], create_date)
        self.assertTrue(params.get('vnp_SecureHash'))
        self.assertTrue(vnpay.verify_vnpay_response({k: v[0] for k, v in params.items()}))

    def test_invalid_signature_is_rejected(self):
        self.assertFalse(vnpay.verify_vnpay_response({'vnp_TxnRef': 'ABC123', 'vnp_SecureHash': '0' * 128}))

    def test_missing_config_raises_clear_error(self):
        with override_settings(VNPAY_TMN_CODE='', VNPAY_HASH_SECRET_KEY=''):
            with self.assertRaises(vnpay.VNPayError):
                vnpay.build_vnpay_payment_url(amount=1000, order_info='x', txn_ref='A')


class ManagementApiTests(APITestCase):
    def setUp(self):
        self.manager = UserAccount.objects.create_user('mgr', password='Abcdef12!x', role='QL')
        self.waiter = UserAccount.objects.create_user('wtr', password='Abcdef12!x', role='PV')
        self.table = Table.objects.create(area='A')
        self.cat = Category.objects.create(name='Chính')
        self.dish = MenuItem.objects.create(category=self.cat, name='Phở', price=Decimal('85000'))

    def _paid_order(self, qty=2, refunded=0):
        order = Order.objects.create(table=self.table, status='completed', subtotal_amount=85000 * qty, total_amount=85000 * qty)
        OrderItem.objects.create(order=order, menu_item=self.dish, quantity=qty, unit_price=self.dish.price, status='served')
        Payment.objects.create(order=order, method='cash', amount=85000 * qty, status='success', transaction_id=f'T{order.id}',
                               refunded_amount=refunded, paid_at=__import__('django').utils.timezone.now())
        return order

    def test_report_periods_best_sellers_and_peak_hours(self):
        self._paid_order(2); self._paid_order(1, refunded=0)
        self.assertIn(self.client.get('/api/reports/summary/').status_code, (401, 403))
        self.client.force_authenticate(self.manager)
        day = self.client.get('/api/reports/summary/', {'period': 'day'}).data
        self.assertEqual(day['revenue'], 255000)
        self.assertEqual(day['paid_orders'], 2)
        self.assertEqual(day['avg_order'], 127500)
        self.assertEqual(len(day['series']), 24)
        self.assertEqual(day['best_sellers'][0]['quantity'], 3)
        self.assertEqual(day['best_sellers'][0]['revenue'], 255000)
        self.assertEqual(sum(h['orders'] for h in day['peak_hours']), 2)
        self.assertEqual(len(self.client.get('/api/reports/summary/', {'period': 'week'}).data['series']), 7)
        self.assertEqual(len(self.client.get('/api/reports/summary/', {'period': 'month'}).data['series']), 30)
        self.assertEqual(self.client.get('/api/reports/summary/', {'date_from': '2020-01-01', 'date_to': '2020-01-10'}).data['revenue'], 0)

    def test_report_subtracts_refunds(self):
        self._paid_order(2, refunded=70000)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get('/api/reports/summary/', {'period': 'day'}).data['revenue'], 100000)

    def test_staff_accounts_manager_only_and_safe(self):
        self.client.force_authenticate(self.waiter)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)
        self.client.force_authenticate(self.manager)
        r = self.client.post('/api/users/', {'username': 'chef1', 'role': 'BEP', 'password': 'Abcdef12!x', 'first_name': 'Bếp'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn('password', r.data)
        self.assertTrue(UserAccount.objects.get(username='chef1').check_password('Abcdef12!x'))
        self.assertEqual(self.client.post('/api/users/', {'username': 'x', 'role': 'PV'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/users/', {'username': 'y', 'role': 'PV', 'password': '123'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/{r.data['id']}/", {'is_active': False}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'/api/users/{self.manager.id}/', {'is_active': False}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f"/api/users/{r.data['id']}/").status_code, 405)

    def test_promotion_crud_validation_and_visibility(self):
        now = __import__('django').utils.timezone.now()
        body = {'code': ' sale10 ', 'discount_type': 'percent', 'value': 10, 'start_date': (now - timedelta(days=1)).isoformat(), 'end_date': (now + timedelta(days=5)).isoformat(), 'is_active': True}
        self.assertEqual(self.client.post('/api/promotions/', body, format='json').status_code, 403 if False else self.client.post('/api/promotions/', body, format='json').status_code)
        self.client.force_authenticate(self.manager)
        r = self.client.post('/api/promotions/', body, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['code'], 'SALE10')
        self.assertEqual(self.client.post('/api/promotions/', {**body, 'code': 'BAD', 'value': 150}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/promotions/', {**body, 'code': 'BAD2', 'end_date': (now - timedelta(days=3)).isoformat()}, format='json').status_code, 400)
        off = self.client.patch(f"/api/promotions/{r.data['id']}/", {'is_active': False}, format='json')
        self.assertEqual(off.status_code, 200)
        self.assertEqual(len(self.client.get('/api/promotions/').data), 1)   # quản lý vẫn thấy mã đã tắt
        self.client.force_authenticate(None)
        self.assertEqual(len(self.client.get('/api/promotions/').data), 0)   # khách thì không

    def test_menu_item_edit_and_protected_delete(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(f'/api/menu-items/{self.dish.id}/', {'price': 90000}, format='json').status_code, 200)
        self._paid_order(1)
        gone = self.client.delete(f'/api/menu-items/{self.dish.id}/')
        self.assertEqual(gone.status_code, 409)
        fresh = MenuItem.objects.create(category=self.cat, name='Gỏi', price=50000)
        self.assertEqual(self.client.delete(f'/api/menu-items/{fresh.id}/').status_code, 204)
        self.assertEqual(self.client.delete(f'/api/categories/{self.cat.id}/').status_code, 400)

    def test_review_flow(self):
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        order = self._paid_order(1)
        item = order.items.first()
        r = self.client.post('/api/reviews/', {'order_item': item.id, 'rating': 5, 'comment': 'Ngon'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['menu_item_name'], 'Phở')
        self.assertEqual(self.client.post('/api/reviews/', {'order_item': item.id, 'rating': 4}, format='json').status_code, 400)
        self.assertEqual(len(self.client.get('/api/reviews/', {'order_id': order.id}).data), 1)
        unserved = Order.objects.create(table=self.table, status='pending')
        raw = OrderItem.objects.create(order=unserved, menu_item=self.dish, quantity=1, unit_price=1, status='cooking')
        self.assertEqual(self.client.post('/api/reviews/', {'order_item': raw.id, 'rating': 5}, format='json').status_code, 400)

    def test_orders_filter_payments_list_and_audit(self):
        order = self._paid_order(1)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get('/api/orders/', {'q': order.id}).data[0]['payment_status'], 'success')
        self.assertEqual(len(self.client.get('/api/orders/', {'date_from': '2999-01-01'}).data), 0)
        self.assertEqual(len(self.client.get('/api/payments/', {'method': 'cash'}).data), 1)
        self.assertEqual(len(self.client.get('/api/payments/', {'method': 'vnpay'}).data), 0)
        self.client.post(f'/api/menu-items/{self.dish.id}/', {}, format='json')
        self.client.patch(f'/api/menu-items/{self.dish.id}/', {'price': 99000}, format='json')
        self.assertEqual(self.client.post('/api/audit-logs/', {'action': 'SWITCH_MODE', 'mode': 'waiter'}, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/audit-logs/', {'action': 'HACK'}, format='json').status_code, 400)
        actions = [x['action'] for x in self.client.get('/api/audit-logs/').data]
        self.assertIn('MENU_ITEM_UPDATE', actions)
        self.assertIn('SWITCH_MODE', actions)
        self.client.force_authenticate(self.waiter)
        self.assertEqual(self.client.get('/api/audit-logs/').status_code, 403)
        self.assertEqual(self.client.get('/api/payments/').status_code, 403)


class CustomerAndSecurityTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.table = Table.objects.create(area='A')
        self.other = Table.objects.create(area='B')
        cat = Category.objects.create(name='Chính')
        self.pho = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('100000'))
        self.bun = MenuItem.objects.create(category=cat, name='Bún', price=Decimal('50000'))
        self.manager = UserAccount.objects.create_user('mgr', password='Abcdef12!x', role='QL')
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)

    def _order(self):
        r = self.client.post('/api/orders/', {'table_id': self.table.id, 'items': [
            {'menu_item_id': self.pho.id, 'quantity': 1, 'note': 'ít cay'}, {'menu_item_id': self.bun.id, 'quantity': 2}]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_customer_cancels_pending_item_and_totals_follow(self):
        order = self._order()
        pho = next(i for i in order['items'] if i['menu_item'] == self.pho.id)
        self.assertEqual(self.client.post(f"/api/order-items/{pho['id']}/cancel/", {}, format='json', HTTP_X_TABLE_TOKEN=make_table_token(self.other)).status_code, 403)
        r = self.client.post(f"/api/order-items/{pho['id']}/cancel/", {}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(int(r.data['total_amount']), 100000)
        self.assertEqual(len(r.data['items']), 1)

    def test_cannot_cancel_item_once_cooking_and_last_item_cancels_order(self):
        order = self._order()
        a, b = order['items']
        OrderItem.objects.filter(pk=a['id']).update(status='cooking')
        self.assertEqual(self.client.post(f"/api/order-items/{a['id']}/cancel/", {}, format='json').status_code, 400)
        self.client.post(f"/api/order-items/{b['id']}/cancel/", {}, format='json')
        OrderItem.objects.filter(pk=a['id']).update(status='pending')
        r = self.client.post(f"/api/order-items/{a['id']}/cancel/", {}, format='json')
        self.assertEqual(r.data['status'], 'cancelled')
        self.table.refresh_from_db(); self.assertEqual(self.table.status, 'empty')

    def test_percent_promotion_recomputed_when_items_added_and_pending_cash_follows(self):
        now = __import__('django').utils.timezone.now()
        Promotion.objects.create(code='P10', discount_type='percent', value=10, start_date=now - timedelta(days=1), end_date=now + timedelta(days=1))
        order = self._order()                                        # 200.000
        self.client.post(f"/api/orders/{order['id']}/apply-promotion/", {'code': 'p10'}, format='json')
        pay = self.client.post('/api/payments/create/', {'order_id': order['id'], 'method': 'cash'}, format='json').data
        self.assertEqual(int(pay['amount']), 180000)
        r = self.client.post(f"/api/orders/{order['id']}/add-items/", {'items': [{'menu_item_id': self.pho.id, 'quantity': 1}]}, format='json')
        self.assertEqual(int(r.data['subtotal_amount']), 300000)
        self.assertEqual(int(r.data['discount_amount']), 30000)       # giảm 10% theo tạm tính mới
        self.assertEqual(int(r.data['total_amount']), 270000)
        self.assertEqual(int(Payment.objects.get(pk=pay['id']).amount), 270000)   # giao dịch chờ không bị lệch tiền

    def test_menu_items_show_average_rating(self):
        order = Order.objects.create(table=self.table, status='completed')
        self.client.get('/api/menu-items/')   # làm nóng cache: review mới phải làm cache mất hiệu lực
        for rating in (5, 4):
            item = OrderItem.objects.create(order=order, menu_item=self.pho, quantity=1, unit_price=1, status='served')
            self.client.post('/api/reviews/', {'order_item': item.id, 'rating': rating}, format='json')
        data = {m['name']: m for m in self.client.get('/api/menu-items/').data}
        self.assertEqual(data['Phở']['avg_rating'], 4.5)
        self.assertEqual(data['Phở']['review_count'], 2)
        self.assertIsNone(data['Bún']['avg_rating'])
        self.assertEqual(len(self.client.get('/api/reviews/', {'rating': 5}).data), 1)

    def test_reauth_and_change_password(self):
        self.assertEqual(self.client.post('/api/auth/reauth/', {'password': 'x'}, format='json').status_code, 401)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post('/api/auth/reauth/', {'password': 'sai'}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/auth/reauth/', {'password': 'Abcdef12!x'}, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/change-password/', {'old_password': 'sai', 'new_password': 'Newpass99!x'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/change-password/', {'old_password': 'Abcdef12!x', 'new_password': '123'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/change-password/', {'old_password': 'Abcdef12!x', 'new_password': 'Newpass99!x'}, format='json').status_code, 200)
        self.manager.refresh_from_db(); self.assertTrue(self.manager.check_password('Newpass99!x'))
        self.assertIn('REAUTH_FAILED', [x['action'] for x in self.client.get('/api/audit-logs/').data])

    def test_login_is_rate_limited(self):
        codes = [self.client.post('/api/auth/login/', {'username': 'mgr', 'password': 'sai'}, format='json').status_code for _ in range(12)]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertIn(429, codes[10:])


    # ---- BR-02: khách chỉ thao tác trong phạm vi bàn của mình
    def test_customer_is_confined_to_own_table(self):
        order = self._order()
        stranger = {'HTTP_X_TABLE_TOKEN': make_table_token(self.other)}
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}/", **stranger).status_code, 403)
        self.assertEqual(self.client.post(f"/api/orders/{order['id']}/add-items/", {'items': [{'menu_item_id': self.pho.id, 'quantity': 1}]}, format='json', **stranger).status_code, 403)
        self.assertEqual(self.client.post(f"/api/orders/{order['id']}/apply-promotion/", {'code': 'X'}, format='json', **stranger).status_code, 403)
        self.assertEqual(self.client.post('/api/payments/create/', {'order_id': order['id'], 'method': 'cash'}, format='json', **stranger).status_code, 403)
        self.assertEqual(self.client.get(f"/api/tables/{self.table.id}/current-order/", **stranger).status_code, 403)
        self.assertEqual(self.client.post('/api/staff-calls/', {'table': self.table.id, 'message': 'x'}, format='json', **stranger).status_code, 403)
        self.assertEqual(self.client.post('/api/orders/', {'table_id': self.table.id, 'items': [{'menu_item_id': self.pho.id, 'quantity': 1}]}, format='json', **stranger).status_code, 403)
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}/").status_code, 200)               # đúng bàn thì được
        no_header = {k: v for k, v in self.client.defaults.items() if k != 'HTTP_X_TABLE_TOKEN'}
        anonymous = type(self.client)(); anonymous.defaults = no_header
        self.assertEqual(anonymous.get(f"/api/orders/{order['id']}/").status_code, 403)
        self.client.force_authenticate(self.manager)                                                    # nhân viên không bị giới hạn
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}/", **stranger).status_code, 200)

    # ---- BR-05: khuyến mãi áp dụng cho món
    def test_item_level_promotion_only_discounts_that_dish(self):
        now = __import__('django').utils.timezone.now()
        Promotion.objects.create(code='PHO50', discount_type='percent', value=50, menu_item=self.pho,
                                 start_date=now - timedelta(days=1), end_date=now + timedelta(days=1))
        r = self.client.post('/api/orders/', {'table_id': self.table.id, 'items': [{'menu_item_id': self.bun.id, 'quantity': 2}]}, format='json')
        order_id = r.data['id']
        bad = self.client.post(f'/api/orders/{order_id}/apply-promotion/', {'code': 'PHO50'}, format='json')
        self.assertEqual(bad.status_code, 400)                                  # chưa có món Phở
        self.assertIn('Phở', bad.data['detail'])
        self.client.post(f'/api/orders/{order_id}/add-items/', {'items': [{'menu_item_id': self.pho.id, 'quantity': 1}]}, format='json')
        ok = self.client.post(f'/api/orders/{order_id}/apply-promotion/', {'code': 'pho50'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(int(ok.data['subtotal_amount']), 200000)               # 100.000 phở + 2×50.000 bún
        self.assertEqual(int(ok.data['discount_amount']), 50000)                # chỉ giảm 50% của phở
        self.assertEqual(int(ok.data['total_amount']), 150000)
        more = self.client.post(f'/api/orders/{order_id}/add-items/', {'items': [{'menu_item_id': self.pho.id, 'quantity': 1}]}, format='json')
        self.assertEqual(int(more.data['discount_amount']), 100000)             # 2 phở → giảm 100.000

    def test_manager_can_create_item_level_promotion(self):
        now = __import__('django').utils.timezone.now()
        self.client.force_authenticate(self.manager)
        body = {'code': 'bun20', 'discount_type': 'fixed', 'value': 20000, 'menu_item': self.bun.id,
                'start_date': (now - timedelta(days=1)).isoformat(), 'end_date': (now + timedelta(days=2)).isoformat(), 'is_active': True}
        r = self.client.post('/api/promotions/', body, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['menu_item_name'], 'Bún')


# ---------------- AC-03: đồng bộ real-time qua WebSocket (kết nối thật tới ứng dụng ASGI) ----------------
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken


@override_settings(**VNPAY_SETTINGS)
class RealtimeTests(TransactionTestCase):
    def setUp(self):
        from backend.asgi import application
        self.app = application
        self.table = Table.objects.create(area='A')
        cat = Category.objects.create(name='Chính')
        self.dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))
        self.chef = UserAccount.objects.create_user('chef', password='x', role='BEP')
        self.waiter = UserAccount.objects.create_user('wtr', password='x', role='PV')

    def _socket(self, group, user=None):
        token = f'?token={AccessToken.for_user(user)}' if user else ''
        if group.startswith('table_') and not user:
            token = f'?token={make_table_token(self.table)}'   # WS-02: khách cần token phiên bàn
        return WebsocketCommunicator(self.app, f'/ws/{group}/{token}')

    def test_order_flow_is_pushed_to_kitchen_staff_and_customer(self):
        async_to_sync(self._scenario)()

    async def _scenario(self):
        kitchen = self._socket('kitchen_orders', self.chef)
        staff = self._socket('staff_orders', self.waiter)
        customer = self._socket(f'table_{self.table.id}')
        for comm in (kitchen, staff, customer):
            connected, _ = await comm.connect()
            self.assertTrue(connected)
        # Khách không đăng nhập không được nghe kênh của bếp/nhân viên
        for group in ('kitchen_orders', 'staff_orders'):
            intruder = self._socket(group)
            connected, _ = await intruder.connect()
            self.assertFalse(connected)

        guest = APIClient(); guest.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)
        order = (await sync_to_async(guest.post)('/api/orders/', {'table_id': self.table.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 1}]}, format='json')).data
        for comm in (kitchen, staff, customer):
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'new_order')
            self.assertEqual(msg['order']['id'], order['id'])

        # Bếp đổi trạng thái món → khách và nhân viên thấy ngay
        chef_client = APIClient(); chef_client.force_authenticate(self.chef)
        item_id = order['items'][0]['id']
        await sync_to_async(chef_client.patch)(f'/api/order-items/{item_id}/status/', {'status': 'cooking'}, format='json')
        for comm in (customer, staff, kitchen):
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual((msg['type'], msg['order_item']['status']), ('item_status_updated', 'cooking'))

        # Khách chọn tiền mặt → nhân viên và bàn nhận staff_call; nhân viên thu tiền → mọi phía nhận order_updated
        pay = (await sync_to_async(guest.post)('/api/payments/create/', {'order_id': order['id'], 'method': 'cash'}, format='json')).data
        for comm in (staff, customer):
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'staff_call')
        waiter_client = APIClient(); waiter_client.force_authenticate(self.waiter)
        await sync_to_async(waiter_client.post)(f"/api/payments/{pay['id']}/confirm-cash/")
        for comm in (customer, staff, kitchen):
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'order_updated')
            self.assertEqual((msg['order']['status'], msg['order']['payment_status']), ('completed', 'success'))

        for comm in (kitchen, staff, customer):
            await comm.disconnect()


class LoginPayloadTests(APITestCase):
    def test_login_returns_role_and_superuser_flag(self):
        from django.core.cache import cache
        cache.clear()
        UserAccount.objects.create_superuser('root', password='Abcdef12!x', role='PV')   # giống tài khoản admin có vai trò PV
        r = self.client.post('/api/auth/login/', {'username': 'root', 'password': 'Abcdef12!x'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['user']['is_superuser'])
        self.assertEqual(r.data['user']['role'], 'PV')


class KitchenApiTests(APITestCase):
    def test_kitchen_can_lock_dish_and_customers_stop_seeing_it(self):
        table = Table.objects.create(area='A')
        cat = Category.objects.create(name='Món nướng')
        dish = MenuItem.objects.create(category=cat, name='Cá hồi', price=Decimal('120000'))
        chef = UserAccount.objects.create_user('chef', password='x', role='BEP')
        guest = APIClient(); guest.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(table)
        self.assertIn(guest.post(f'/api/menu-items/{dish.id}/availability/', {'is_available': False}, format='json').status_code, (401, 403))
        self.client.force_authenticate(chef)
        r = self.client.post(f'/api/menu-items/{dish.id}/availability/', {'is_available': False}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data['is_available'])
        self.assertEqual(guest.get('/api/menu-items/').data, [])                                       # khách không còn thấy món
        self.assertEqual(guest.post('/api/orders/', {'table_id': table.id, 'items': [{'menu_item_id': dish.id, 'quantity': 1}]}, format='json').status_code, 404)
        self.assertTrue(self.client.post(f'/api/menu-items/{dish.id}/availability/', {'is_available': True}, format='json').data['is_available'])
        order = guest.post('/api/orders/', {'table_id': table.id, 'items': [{'menu_item_id': dish.id, 'quantity': 1}]}, format='json').data
        self.assertEqual((order['items'][0]['category'], order['items'][0]['category_name']), (cat.id, 'Món nướng'))   # bếp lọc theo danh mục
        self.assertIn('MENU_ITEM_AVAILABILITY', [x['action'] for x in self._audit()])

    def _audit(self):
        self.client.force_authenticate(UserAccount.objects.create_user('boss', password='x', role='QL'))
        return self.client.get('/api/audit-logs/').data


class BrdExtraTests(APITestCase):
    def setUp(self):
        self.table = Table.objects.create(area='A')
        cat = Category.objects.create(name='Chính')
        self.dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('50000'))
        self.client.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(self.table)

    def test_second_order_merges_into_open_order(self):
        body = {'table_id': self.table.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 1}]}
        first = self.client.post('/api/orders/', body, format='json')
        second = self.client.post('/api/orders/', body, format='json')
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(int(second.data['total_amount']), 100000)

    def test_table_with_orders_cannot_be_deleted_or_emptied(self):
        self.client.post('/api/orders/', {'table_id': self.table.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 1}]}, format='json')
        self.client.force_authenticate(UserAccount.objects.create_user('mgr', password='x', role='QL'))
        self.assertEqual(self.client.patch(f'/api/tables/{self.table.id}/status/', {'status': 'empty'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/tables/{self.table.id}/').status_code, 400)

    def test_manager_cannot_grant_admin(self):
        self.client.force_authenticate(UserAccount.objects.create_user('mgr', password='x', role='QL'))
        r = self.client.post('/api/users/', {'username': 'boss', 'role': 'AD', 'password': 'Abcdef12!x'}, format='json')
        self.assertEqual(r.status_code, 400)
