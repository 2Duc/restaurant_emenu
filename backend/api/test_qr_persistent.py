"""QR bàn dùng lâu dài: qr_token cố định, ảnh QR lưu bền, in hàng loạt (PNG/PDF/zip)."""
import io
import shutil
import tempfile
import zipfile
from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Category, MenuItem, Table, UserAccount
from .services.qr_service import table_qr_file
from .services.table_token import make_table_token

MEDIA = tempfile.mkdtemp(prefix='qr_test_media_')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA, FRONTEND_BASE_URL='http://localhost:5173', PUBLIC_BASE_URL='')
class QrPersistentTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.t1 = Table.objects.create(area='A')
        self.t2 = Table.objects.create(area='B')
        cat = Category.objects.create(name='Chính')
        self.dish = MenuItem.objects.create(category=cat, name='Phở', price=Decimal('85000'))

    def staff(self, role='QL'):
        c = APIClient()
        c.force_authenticate(UserAccount.objects.create_user(f'q_{role}_{UserAccount.objects.count()}', password='x', role=role))
        return c

    def guest(self, table):
        c = APIClient()
        c.defaults['HTTP_X_TABLE_TOKEN'] = make_table_token(table)
        return c

    def can_scan(self, table, key):
        return APIClient().post('/api/tables/session/', {'table_id': table.id, 'k': key}, format='json').status_code == 200

    def test_qr_link_survives_order_payment_cleaning_empty(self):
        """Đặt món -> thanh toán tiền mặt -> bàn cleaning -> empty: qr_token không đổi, quét lại QR cũ vẫn vào được."""
        key = self.t1.qr_token
        self.assertTrue(self.can_scan(self.t1, key))
        r = self.guest(self.t1).post('/api/orders/', {'table_id': self.t1.id, 'items': [{'menu_item_id': self.dish.id, 'quantity': 1}]}, format='json')
        self.assertIn(r.status_code, (200, 201))
        order_id = r.data['id']
        pay = self.guest(self.t1).post('/api/payments/create/', {'order_id': order_id, 'method': 'cash'}, format='json').data
        self.assertEqual(self.staff('PV').post(f"/api/payments/{pay['id']}/confirm-cash/").status_code, 200)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, 'cleaning')
        self.assertEqual(self.t1.qr_token, key)
        self.assertTrue(self.can_scan(self.t1, key))
        self.assertEqual(self.staff('PV').patch(f'/api/tables/{self.t1.id}/status/', {'status': 'empty'}, format='json').status_code, 200)
        self.assertEqual(self.staff('QL').patch(f'/api/tables/{self.t1.id}/', {'capacity': 6, 'area': 'Z'}, format='json').status_code, 200)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.qr_token, key)
        self.assertTrue(self.can_scan(self.t1, key))
        # xem / in QR cũng không xoay token
        self.staff('QL').get('/api/tables/qr-codes/')
        self.staff('QL').get('/api/tables/qr-pdf/')
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.qr_token, key)

    def test_only_rotate_endpoint_changes_token_and_old_qr_dies(self):
        key = self.t1.qr_token
        self.assertEqual(self.staff('PV').post(f'/api/tables/{self.t1.id}/rotate-qr/').status_code, 403)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.qr_token, key)
        self.assertEqual(self.staff('QL').post(f'/api/tables/{self.t1.id}/rotate-qr/').status_code, 200)
        self.t1.refresh_from_db()
        self.assertNotEqual(self.t1.qr_token, key)
        self.assertFalse(self.can_scan(self.t1, key))
        self.assertTrue(self.can_scan(self.t1, self.t1.qr_token))

    def test_qr_image_file_persisted_and_regenerated_only_when_token_or_base_change(self):
        base = 'http://192.168.1.5:5173'
        p1 = table_qr_file(self.t1, base)
        mtime = p1.stat().st_mtime_ns
        self.assertEqual(table_qr_file(self.t1, base), p1)
        self.assertEqual(p1.stat().st_mtime_ns, mtime)   # không sinh lại
        p2 = table_qr_file(self.t1, 'https://abc.example.com')
        self.assertNotEqual(p1, p2)                      # đổi base -> ảnh khác (link đúng)
        self.t1.qr_token = 'moi-moi-moi'
        p3 = table_qr_file(self.t1, 'https://abc.example.com')
        self.assertNotEqual(p2, p3)
        self.assertFalse(p2.exists())                    # file cũ của bàn được dọn
        self.assertNotIn(self.t1.qr_token, p3.name)      # tên file không lộ token

    def test_qr_codes_payload_uses_requested_base_and_reports_default(self):
        r = self.staff('QL').get('/api/tables/qr-codes/?base_url=http://10.0.0.9:8088')
        item = next(x for x in r.data if x['table_id'] == self.t1.id)
        self.assertEqual(item['url'], f'http://10.0.0.9:8088/table/{self.t1.id}?k={self.t1.qr_token}')
        self.assertEqual(item['base_url'], 'http://10.0.0.9:8088')
        self.assertEqual(item['default_base_url'], 'http://localhost:5173')
        self.assertTrue(item['qr_image'].startswith('data:image/png;base64,'))

    @override_settings(PUBLIC_BASE_URL='https://abc.example.com/')
    def test_public_base_url_is_default(self):
        item = self.staff('QL').get(f'/api/tables/{self.t1.id}/qr/').data
        self.assertEqual(item['url'], f'https://abc.example.com/table/{self.t1.id}?k={self.t1.qr_token}')

    def test_downloads_png_pdf_zip(self):
        ql = self.staff('QL')
        r = ql.get(f'/api/tables/{self.t1.id}/qr-png/')
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/png'))
        self.assertTrue(r.content.startswith(b'\x89PNG'))
        card = ql.get(f'/api/tables/{self.t1.id}/qr-png/?card=1')
        self.assertTrue(card.content.startswith(b'\x89PNG'))
        self.assertGreater(len(card.content), len(r.content) // 4)
        pdf = ql.get('/api/tables/qr-pdf/')
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        sel = ql.get(f'/api/tables/qr-zip/?ids={self.t1.id},{self.t2.id}')
        names = zipfile.ZipFile(io.BytesIO(sel.content)).namelist()
        self.assertEqual(sorted(names), sorted([f'the-ban-{self.t1.id}.png', f'the-ban-{self.t2.id}.png']))
        only = ql.get(f'/api/tables/qr-zip/?ids={self.t2.id}')
        self.assertEqual(zipfile.ZipFile(io.BytesIO(only.content)).namelist(), [f'the-ban-{self.t2.id}.png'])

    def test_download_permissions_and_bad_params(self):
        for url in (f'/api/tables/{self.t1.id}/qr-png/', '/api/tables/qr-pdf/', '/api/tables/qr-zip/'):
            self.assertIn(APIClient().get(url).status_code, (401, 403))
            self.assertIn(self.guest(self.t1).get(url).status_code, (401, 403))
        self.assertEqual(self.staff('QL').get('/api/tables/qr-pdf/?ids=abc').status_code, 400)
        self.assertEqual(self.staff('QL').get('/api/tables/qr-pdf/?ids=99999').status_code, 404)

    def test_many_tables_pdf_multiple_pages(self):
        for _ in range(5):
            Table.objects.create()
        pdf = self.staff('QL').get('/api/tables/qr-pdf/').content
        self.assertGreaterEqual(pdf.count(b'/Type /Page\n') + pdf.count(b'/Type /Page '), 2)
