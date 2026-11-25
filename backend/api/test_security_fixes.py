"""Test cho các bản vá bảo mật (RATE-01/03, AUTH-05, WS-02, PAY-02, tham số sai kiểu, HSTS, renderer)."""
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from unittest import mock

from channels.testing import WebsocketCommunicator
from asgiref.sync import async_to_sync, sync_to_async
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import AuditLog, Category, MenuItem, Order, OrderItem, Payment, Review, StaffCall, Table, UserAccount
from .services.table_token import MAX_AGE_SECONDS, make_table_token, verify_table_token

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOW_RATES = {'login': '10/min', 'reauth': '10/min', 'customer': '5/min', 'order_create': '2/min',
             'staff_call': '1/min', 'review': '1/min', 'table_session': '3/min'}


def low_rest_framework(**extra):
    from django.conf import settings
    cfg = dict(settings.REST_FRAMEWORK)
    cfg['DEFAULT_THROTTLE_RATES'] = LOW_RATES
    cfg.update(extra)
    return cfg


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.table = Table.objects.create(area='A')
        self.other = Table.objects.create(area='B')
        cat = Category.objects.create(name='Chính')
        self.dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))
        self.body = {'table_id': self.table.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 1}]}

    def guest(self, table=None):
        c = APIClient()
        c.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(table or self.table)
        return c

    def staff(self, role='QL'):
        c = APIClient()
        c.force_authenticate(UserAccount.objects.create_user(f'u_{role}_{UserAccount.objects.count()}', password='x', role=role))
        return c

    def make_order(self):
        return self.guest().post('/api/orders/', self.body, format='json').data


class LoginThrottleXffTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_spoofed_xff_cannot_bypass_login_throttle(self):
        """RATE-01: 11+ lần login sai với X-Forwarded-For khác nhau vẫn bị 429."""
        codes = [self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, format='json',
                                  HTTP_X_FORWARDED_FOR=f'10.0.{i}.{i}').status_code for i in range(13)]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10:], [429] * 3)

    @override_settings(REST_FRAMEWORK={'NUM_PROXIES': 1, 'DEFAULT_THROTTLE_RATES': {'login': '10/min'}})
    def test_trusted_proxy_count_uses_last_hop(self):
        """NUM_PROXIES=1: DRF lấy IP proxy ghi thêm (cuối chuỗi) -> client giả đầu chuỗi vẫn bị chặn, IP thật khác nhau thì độc lập."""
        for i in range(10):
            self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, format='json',
                             HTTP_X_FORWARDED_FOR=f'6.6.6.{i}, 1.2.3.4')
        r = self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, format='json', HTTP_X_FORWARDED_FOR='7.7.7.7, 1.2.3.4')
        self.assertEqual(r.status_code, 429)
        r = self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, format='json', HTTP_X_FORWARDED_FOR='7.7.7.7, 5.6.7.8')
        self.assertEqual(r.status_code, 401)


class TableTokenTests(Base):
    def test_qr_token_unique_random_for_every_table(self):
        """Mọi bàn có qr_token riêng, không rỗng."""
        tokens = list(Table.objects.values_list('qr_token', flat=True))
        self.assertEqual(len(set(tokens)), len(tokens))
        self.assertTrue(all(len(t) >= 20 for t in tokens))

    def test_session_exchange_ok_and_token_works(self):
        r = self.client.post('/api/tables/session/', {'table_id': self.table.id, 'k': self.table.qr_token}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['table_id'], self.table.id)
        self.assertEqual(verify_table_token(r.data['token']), self.table.id)
        c = APIClient(); c.defaults['HTTP_X_TABLE_TOKEN'] = r.data['token']
        self.assertEqual(c.post('/api/orders/', self.body, format='json').status_code, 201)

    def test_session_exchange_rejects_bad_input(self):
        url = '/api/tables/session/'
        for body in ({'table_id': self.table.id, 'k': 'wrong'}, {'table_id': self.table.id}, {'k': self.table.qr_token},
                     {'table_id': 99999, 'k': self.table.qr_token}, {'table_id': self.other.id, 'k': self.table.qr_token},
                     {'table_id': self.table.id, 'k': ['x']}, {'table_id': self.table.id, 'k': None}):
            self.assertEqual(self.client.post(url, body, format='json').status_code, 403, body)
        for bad in ('abc', '1 OR 1=1', 10 ** 30):
            self.assertEqual(self.client.post(url, {'table_id': bad, 'k': 'x'}, format='json').status_code, 400, bad)

    def test_session_exchange_is_throttled(self):
        """Dò mã k bị giới hạn (table_session) theo IP."""
        with override_settings(REST_FRAMEWORK=low_rest_framework()):
            cache.clear()
            codes = [self.client.post('/api/tables/session/', {'table_id': self.table.id, 'k': f'g{i}'}, format='json').status_code for i in range(5)]
        self.assertEqual(codes, [403, 403, 403, 429, 429])

    def test_customer_endpoints_require_valid_token(self):
        """Không token / X-Table-Id tự khai / token rác -> 403 ở mọi API khách; có token -> qua."""
        order = self.make_order()
        item = order['items'][0]['id']
        calls = [
            ('post', '/api/orders/', self.body), ('get', f"/api/orders/{order['id']}/", None),
            ('post', f"/api/orders/{order['id']}/add-items/", {'items': self.body['items']}),
            ('post', f"/api/order-items/{item}/cancel/", {}), ('post', f"/api/orders/{order['id']}/apply-promotion/", {'code': ''}),
            ('post', '/api/payments/create/', {'order_id': order['id'], 'method': 'cash'}),
            ('post', '/api/staff-calls/', {'table': self.table.id, 'message': 'x'}),
            ('post', '/api/reviews/', {'order_item': item, 'rating': 5}),
            ('get', f'/api/tables/{self.table.id}/current-order/', None),
        ]
        for headers in ({}, {'HTTP_X_TABLE_ID': str(self.table.id)}, {'HTTP_X_TABLE_TOKEN': 'garbage'}):
            c = APIClient()
            for method, url, data in calls:
                r = getattr(c, method)(url, data, format='json', **headers) if data is not None else getattr(c, method)(url, **headers)
                self.assertEqual(r.status_code, 403, (method, url, headers, r.status_code))
        g = self.guest()
        self.assertEqual(g.get(f"/api/orders/{order['id']}/").status_code, 200)
        self.assertEqual(g.get(f'/api/tables/{self.table.id}/current-order/').status_code, 200)
        self.assertEqual(self.client.get('/api/menu-items/').status_code, 200)   # menu vẫn công khai

    def test_token_of_other_table_is_rejected(self):
        order = self.make_order()
        self.assertEqual(self.guest(self.other).get(f"/api/orders/{order['id']}/").status_code, 403)

    def test_token_expires_after_six_hours(self):
        import time as _time
        token = make_table_token(self.table)
        real = _time.time()
        with mock.patch('django.core.signing.time.time', return_value=real + MAX_AGE_SECONDS + 5):
            self.assertIsNone(verify_table_token(token))
        with mock.patch('django.core.signing.time.time', return_value=real + MAX_AGE_SECONDS - 60):
            self.assertEqual(verify_table_token(token), self.table.id)

    def test_forged_token_signed_with_other_salt_rejected(self):
        from django.core import signing
        forged = signing.TimestampSigner(salt='other').sign(f'{self.table.id}:abc')
        self.assertIsNone(verify_table_token(forged))

    def test_rotate_qr_invalidates_old_link_and_sessions_and_is_audited(self):
        old_key = self.table.qr_token
        old_tok = make_table_token(self.table)
        r = self.staff('QL').post(f'/api/tables/{self.table.id}/rotate-qr/')
        self.assertEqual(r.status_code, 200, r.data)
        self.table.refresh_from_db()
        self.assertNotEqual(self.table.qr_token, old_key)
        self.assertIn(f'k={self.table.qr_token}', r.data['url'])
        self.assertTrue(AuditLog.objects.filter(action='TABLE_QR_ROTATE').exists())
        # QR cũ + token cũ hết hiệu lực
        self.assertEqual(self.client.post('/api/tables/session/', {'table_id': self.table.id, 'k': old_key}, format='json').status_code, 403)
        c = APIClient(); c.defaults['HTTP_X_TABLE_TOKEN'] = old_tok
        self.assertEqual(c.post('/api/orders/', self.body, format='json').status_code, 403)
        # QR mới dùng được
        self.assertEqual(self.client.post('/api/tables/session/', {'table_id': self.table.id, 'k': self.table.qr_token}, format='json').status_code, 200)

    def test_rotate_qr_permissions(self):
        url = f'/api/tables/{self.table.id}/rotate-qr/'
        self.assertEqual(self.staff('PV').post(url).status_code, 403)
        self.assertEqual(self.staff('BEP').post(url).status_code, 403)
        self.assertIn(self.client.post(url).status_code, (401, 403))
        self.assertIn(self.guest().post(url).status_code, (401, 403))
        self.assertEqual(self.staff('AD').post(url).status_code, 200)

    def test_qr_token_never_exposed_by_public_table_api(self):
        for url in (f'/api/tables/{self.table.id}/', f'/api/tables/by-number/{self.table.number}/'):
            body = json.dumps(self.client.get(url).json())
            self.assertNotIn(self.table.qr_token, body)
        table = Table.objects.get(pk=self.table.pk)
        self.staff('PV').get(f'/api/tables/{table.id}/qr/')
        self.assertNotIn(table.qr_token, json.dumps(self.client.get(f'/api/tables/{table.id}/').json()))

    def test_staff_needs_no_table_token(self):
        self.assertEqual(self.staff('PV').post('/api/orders/', self.body, format='json').status_code, 201)


class CustomerThrottleTests(Base):
    def setUp(self):
        super().setUp()
        self.rf = override_settings(REST_FRAMEWORK=low_rest_framework())
        self.rf.enable(); self.addCleanup(self.rf.disable)
        cache.clear()

    def test_order_create_throttled(self):
        g = self.guest()
        codes = [g.post('/api/orders/', self.body, format='json').status_code for _ in range(4)]
        self.assertEqual(codes[:2], [201, 200])
        self.assertEqual(codes[2:], [429, 429])

    def test_throttle_is_per_table_not_per_ip(self):
        """Hai bàn cùng IP không chiếm quota của nhau."""
        for _ in range(3):
            self.guest().post('/api/orders/', self.body, format='json')
        other_body = {'table_id': self.other.id, 'items': self.body['items']}
        self.assertEqual(self.guest(self.other).post('/api/orders/', other_body, format='json').status_code, 201)

    def test_staff_call_throttled(self):
        g = self.guest()
        codes = [g.post('/api/staff-calls/', {'table': self.table.id, 'message': 'x'}, format='json').status_code for _ in range(3)]
        self.assertEqual(codes[0], 201)
        self.assertEqual(codes[1:], [429, 429])

    def test_review_throttled(self):
        order = self.make_order()
        OrderItem.objects.filter(pk=order['items'][0]['id']).update(status='served')
        Order.objects.filter(pk=order['id']).update(status='completed')
        cache.clear()
        g = self.guest()
        codes = [g.post('/api/reviews/', {'order_item': order['items'][0]['id'], 'rating': 5}, format='json').status_code for _ in range(3)]
        self.assertEqual(codes[0], 201)
        self.assertEqual(codes[1:].count(429), 2)

    def test_generic_customer_scope_throttles_reads(self):
        g = self.guest()
        Order.objects.create(table=self.table, status='pending')
        codes = [g.get(f'/api/tables/{self.table.id}/current-order/').status_code for _ in range(7)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5:], [429, 429])

    def test_staff_not_throttled(self):
        s = self.staff('PV')
        codes = [s.post('/api/staff-calls/', {'table': self.table.id, 'message': 'x'}, format='json').status_code for _ in range(1)]
        self.assertEqual(codes, [201])
        for _ in range(8):
            self.assertEqual(self.staff('QL').get('/api/orders/').status_code, 200)


class BadParameterTests(Base):
    def test_query_params_wrong_type_give_400(self):
        s = self.staff('QL')
        for url in ('/api/orders/?table_id=abc', "/api/orders/?table_id=1' OR '1'='1", '/api/orders/?limit=abc',
                    '/api/orders/?table_id=' + '9' * 40, '/api/reviews/?order_id=abc', '/api/reviews/?menu_item=x',
                    '/api/reviews/?rating=five', '/api/payments/?limit=abc', '/api/audit-logs/?limit=abc'):
            self.assertEqual(s.get(url).status_code, 400, url)
        for url in ('/api/orders/?table_id=1', '/api/orders/?limit=5', '/api/reviews/?rating=5', '/api/audit-logs/?limit=5'):
            self.assertEqual(s.get(url).status_code, 200, url)

    def test_review_post_wrong_type_gives_400(self):
        g = self.guest()
        for bad in ('abc', "1 OR 1=1", 10 ** 30, 1.5, True):
            r = g.post('/api/reviews/', {'order_item': bad, 'rating': 5}, format='json')
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(g.post('/api/reviews/', {'order_item': 999999, 'rating': 5}, format='json').status_code, 400)

    def test_staff_call_wrong_type_gives_400(self):
        r = self.guest().post('/api/staff-calls/', {'table': 'abc'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_non_object_json_body_gives_400(self):
        for body in ('[1,2]', '"x"', '5'):
            r = self.guest().post('/api/staff-calls/', body, content_type='application/json')
            self.assertEqual(r.status_code, 400, body)
        r = self.staff('QL').post('/api/orders/', '[1]', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_order_body_bad_types_give_400(self):
        g = self.guest()
        for body in ({'table_id': 'abc', 'items': []}, {'table_id': self.table.id, 'items': [{'menu_item_id': 'x', 'quantity': 1}]},
                     {'table_id': self.table.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 'many'}]}):
            self.assertEqual(g.post('/api/orders/', body, format='json').status_code, 400, body)


def run_settings(env, code='from django.conf import settings as s; import json; print(json.dumps({"mode": s.PAYMENT_GATEWAY_MODE, "renderers": list(s.REST_FRAMEWORK.get("DEFAULT_RENDERER_CLASSES", [])), "hsts": s.SECURE_HSTS_SECONDS, "proxies": s.REST_FRAMEWORK["NUM_PROXIES"]}))'):
    base = {k: v for k, v in os.environ.items() if not k.startswith(('DJANGO_', 'VNPAY_', 'PAYMENT_', 'RAILWAY', 'NUM_PROXIES', 'SECURE_'))}
    base.update({'DJANGO_SETTINGS_MODULE': 'backend.settings', 'DATABASE_URL': 'sqlite:///x.sqlite3', 'DJANGO_SECRET_KEY': 'k' * 40,
                 'VNPAY_TMN_CODE': '', 'VNPAY_HASH_SECRET_KEY': '', 'PAYMENT_GATEWAY_MODE': ''})
    base.update(env)
    return subprocess.run([sys.executable, '-c', 'import django; django.setup()\n' + code], cwd=BACKEND_DIR, env=base, capture_output=True, text=True, timeout=120)


class ProductionSettingsTests(APITestCase):
    def test_debug0_without_gateway_mode_is_config_error(self):
        """PAY-02: DEBUG=0, không đặt PAYMENT_GATEWAY_MODE và thiếu khoá VNPay -> lỗi cấu hình, không tự rơi về mock."""
        p = run_settings({'DJANGO_DEBUG': '0'})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('VNPAY_TMN_CODE', p.stderr)

    def test_debug0_defaults_to_vnpay_with_keys(self):
        p = run_settings({'DJANGO_DEBUG': '0', 'VNPAY_TMN_CODE': 'A', 'VNPAY_HASH_SECRET_KEY': 'B'})
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(data['mode'], 'vnpay')
        self.assertEqual(data['renderers'], ['rest_framework.renderers.JSONRenderer'])   # XSS-06
        self.assertEqual(data['proxies'], 0)                                              # RATE-01 mặc định

    def test_debug0_explicit_mock_allowed(self):
        p = run_settings({'DJANGO_DEBUG': '0', 'PAYMENT_GATEWAY_MODE': 'mock'})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1])['mode'], 'mock')

    def test_invalid_gateway_mode_rejected(self):
        self.assertNotEqual(run_settings({'DJANGO_DEBUG': '1', 'PAYMENT_GATEWAY_MODE': 'momo'}).returncode, 0)

    def test_debug1_keeps_mock_fallback_and_browsable_api(self):
        p = run_settings({'DJANGO_DEBUG': '1'})
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual((data['mode'], data['renderers'], data['hsts']), ('mock', [], 0))

    def test_hsts_on_https_deploy_and_num_proxies_env(self):
        p = run_settings({'DJANGO_DEBUG': '0', 'PAYMENT_GATEWAY_MODE': 'mock', 'RAILWAY_PUBLIC_DOMAIN': 'x.up.railway.app', 'NUM_PROXIES': '1'})
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual((data['hsts'], data['proxies']), (31536000, 1))
        p = run_settings({'DJANGO_DEBUG': '0', 'PAYMENT_GATEWAY_MODE': 'mock', 'SECURE_HSTS_SECONDS': '0', 'RAILWAY_PUBLIC_DOMAIN': 'x.up.railway.app'})
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1])['hsts'], 0)


class MigrationTokenFillTests(APITestCase):
    def test_fill_function_gives_unique_tokens_to_existing_tables(self):
        """Migration 0009: bàn có sẵn (qr_token NULL) được sinh token riêng, không mất dữ liệu."""
        import importlib
        from django.apps import apps
        mod = importlib.import_module('api.migrations.0009_table_qr_token_fill')
        Table.objects.all().delete()
        tables = [Table.objects.create(area=f'Z{i}') for i in range(3)]
        mod.fill_tokens(apps, None)   # không thay đổi token đã có
        self.assertEqual(len(set(Table.objects.values_list('qr_token', flat=True))), 3)
        self.assertEqual(Table.objects.filter(area__startswith='Z').count(), len(tables))


class WsTableTokenTests(TransactionTestCase):
    def test_table_ws_requires_valid_token(self):
        async_to_sync(self._run)()

    async def _run(self):
        from backend.asgi import application
        t1 = await sync_to_async(Table.objects.create)(area='A')
        t2 = await sync_to_async(Table.objects.create)(area='B')
        user = await sync_to_async(UserAccount.objects.create_user)('wsq', password='x', role='BEP')

        async def ok(group, token):
            c = WebsocketCommunicator(application, f'/ws/{group}/' + (f'?token={token}' if token else ''))
            connected, _ = await c.connect()
            if connected:
                await c.disconnect()
            return connected
        tok = make_table_token(t1)
        self.assertTrue(await ok(f'table_{t1.id}', tok))
        self.assertFalse(await ok(f'table_{t1.id}', None))
        self.assertFalse(await ok(f'table_{t2.id}', tok))
        self.assertFalse(await ok(f'table_{t1.id}', tok + 'x'))
        self.assertTrue(await ok(f'table_{t2.id}', str(AccessToken.for_user(user))))


class OrderListPagingTests(Base):
    def test_paginated_active_and_legacy(self):
        o = self.make_order()
        done = Order.objects.create(table=self.other, status=Order.Status.COMPLETED)
        s = self.staff('PV')
        r = s.get('/api/orders/?page=1&page_size=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 2)
        self.assertEqual(len(r.data['results']), 1)
        self.assertIsNotNone(r.data['next'])
        self.assertNotIn('created_by', r.data['results'][0])
        self.assertEqual(s.get('/api/orders/?page=1&page_size=500').data['results'][0]['id'], done.id)
        a = s.get('/api/orders/?active=1').data
        self.assertEqual([x['id'] for x in a], [o['id']])
        self.assertNotIn('menu_item_image', a[0]['items'][0])
        legacy = s.get('/api/orders/').data
        self.assertEqual(len(legacy), 2)
        self.assertIn('menu_item_image', legacy[0]['items'][0] if legacy[0]['items'] else legacy[1]['items'][0])
        self.assertEqual(s.get('/api/orders/?page=abc').status_code, 404)
