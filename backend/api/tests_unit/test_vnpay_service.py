"""Unit test cho api/services/vnpay_services.py."""
import hashlib
import hmac
from datetime import datetime
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qsl, urlparse

import requests
from django.test import SimpleTestCase, override_settings

from ..services import vnpay_services as vnp

CFG = dict(VNPAY_TMN_CODE='TMN', VNPAY_HASH_SECRET_KEY='SECRET', VNPAY_RETURN_URL='http://ret/x',
           VNPAY_PAYMENT_URL='https://pay.test/vpcpay.html', VNPAY_API_URL='https://api.test/merchant')


class HashTests(SimpleTestCase):
    def test_hmacsha512_matches_reference_implementation(self):
        """HMAC-SHA512 trùng kết quả thư viện chuẩn, độ dài 128 hex."""
        out = vnp.hmacsha512('k', 'data')
        self.assertEqual(out, hmac.new(b'k', b'data', hashlib.sha512).hexdigest())
        self.assertEqual(len(out), 128)

    def test_hmacsha512_handles_unicode(self):
        """Dữ liệu tiếng Việt được encode UTF-8 không lỗi."""
        self.assertEqual(len(vnp.hmacsha512('k', 'Thanh toán đơn')), 128)

    def test_encoded_pairs_sorts_drops_empty_and_quotes(self):
        """Sắp theo key, bỏ rỗng/None, quote_plus (space -> +, & -> %26)."""
        out = vnp._encoded_pairs({'b': 'x y', 'a': '1&2', 'c': '', 'd': None, 'e': 0})
        self.assertEqual(out, 'a=1%262&b=x+y&e=0')


@override_settings(**CFG)
class VerifyResponseTests(SimpleTestCase):
    def signed(self, **extra):
        data = {'vnp_TxnRef': 'ORD1', 'vnp_Amount': '1000000', 'vnp_OrderInfo': 'Thanh toan don'}
        data.update(extra)
        data['vnp_SecureHash'] = vnp.hmacsha512('SECRET', vnp._encoded_pairs(data))
        return data

    def test_valid_signature_passes(self):
        """Chữ ký đúng -> True."""
        self.assertTrue(vnp.verify_vnpay_response(self.signed()))

    def test_uppercase_hash_passes(self):
        """Hash viết hoa vẫn hợp lệ (so sánh không phân biệt hoa thường)."""
        data = self.signed()
        data['vnp_SecureHash'] = data['vnp_SecureHash'].upper()
        self.assertTrue(vnp.verify_vnpay_response(data))

    def test_tampered_amount_fails(self):
        """Sửa số tiền sau khi ký -> False."""
        data = self.signed()
        data['vnp_Amount'] = '1'
        self.assertFalse(vnp.verify_vnpay_response(data))

    def test_missing_hash_fails(self):
        """Thiếu vnp_SecureHash -> False."""
        data = self.signed()
        del data['vnp_SecureHash']
        self.assertFalse(vnp.verify_vnpay_response(data))

    def test_secure_hash_type_and_non_vnp_params_ignored(self):
        """vnp_SecureHashType và tham số không bắt đầu bằng vnp_ không ảnh hưởng chữ ký."""
        data = self.signed()
        data['vnp_SecureHashType'] = 'HmacSHA512'
        data['random'] = 'x'
        self.assertTrue(vnp.verify_vnpay_response(data))

    def test_wrong_secret_fails(self):
        """Khoá bí mật khác -> False."""
        data = self.signed()
        with override_settings(VNPAY_HASH_SECRET_KEY='OTHER'):
            self.assertFalse(vnp.verify_vnpay_response(data))

    def test_empty_secret_fails(self):
        """Chưa cấu hình khoá -> luôn False."""
        data = self.signed()
        with override_settings(VNPAY_HASH_SECRET_KEY=''):
            self.assertFalse(vnp.verify_vnpay_response(data))

    def test_accepts_querydict_like_input(self):
        """Nhận được cả QueryDict (dict(...) trả list) mà không ném lỗi."""
        from django.http import QueryDict
        qd = QueryDict(mutable=True)
        qd.update({'vnp_TxnRef': 'ORD1'})
        self.assertFalse(vnp.verify_vnpay_response(qd))


class ClientIpTests(SimpleTestCase):
    def test_ignores_forwarded_by_default(self):
        """NUM_PROXIES=0 -> bỏ qua X-Forwarded-For (client tự gửi), dùng REMOTE_ADDR."""
        r = SimpleNamespace(META={'HTTP_X_FORWARDED_FOR': ' 1.1.1.1 , 2.2.2.2', 'REMOTE_ADDR': '9.9.9.9'})
        self.assertEqual(vnp.get_client_ip(r), '9.9.9.9')

    @override_settings(REST_FRAMEWORK={'NUM_PROXIES': 2})
    def test_uses_forwarded_ip_by_proxy_count(self):
        """NUM_PROXIES=2 -> lấy IP thứ 2 tính từ cuối X-Forwarded-For."""
        r = SimpleNamespace(META={'HTTP_X_FORWARDED_FOR': ' 1.1.1.1 , 2.2.2.2', 'REMOTE_ADDR': '9.9.9.9'})
        self.assertEqual(vnp.get_client_ip(r), '1.1.1.1')

    def test_falls_back_to_remote_addr(self):
        """Không có forwarded -> REMOTE_ADDR."""
        self.assertEqual(vnp.get_client_ip(SimpleNamespace(META={'REMOTE_ADDR': '9.9.9.9'})), '9.9.9.9')

    def test_defaults_to_loopback(self):
        """Không có gì -> 127.0.0.1 (cả khi REMOTE_ADDR rỗng)."""
        self.assertEqual(vnp.get_client_ip(SimpleNamespace(META={})), '127.0.0.1')
        self.assertEqual(vnp.get_client_ip(SimpleNamespace(META={'REMOTE_ADDR': ''})), '127.0.0.1')


class TxnRefTests(SimpleTestCase):
    def test_format_and_prefix(self):
        """Mã bắt đầu ORD<id>T, chỉ gồm chữ/số, dưới 100 ký tự."""
        ref = vnp.new_txn_ref(42)
        self.assertTrue(ref.startswith('ORD42T'))
        self.assertTrue(ref.isalnum())
        self.assertLess(len(ref), 100)

    def test_unique_per_call(self):
        """Gọi liên tiếp 200 lần không trùng."""
        self.assertEqual(len({vnp.new_txn_ref(1) for _ in range(200)}), 200)


@override_settings(**CFG)
class BuildUrlTests(SimpleTestCase):
    def build(self, **kw):
        args = dict(amount=85000, order_info='Thanh toan', txn_ref='ORD1T1')
        args.update(kw)
        url, created = vnp.build_vnpay_payment_url(**args)
        return url, created, dict(parse_qsl(urlparse(url).query))

    def test_url_contains_amount_x100_and_valid_hash(self):
        """Số tiền nhân 100; chữ ký trong URL verify được."""
        url, created, q = self.build()
        self.assertTrue(url.startswith('https://pay.test/vpcpay.html?'))
        self.assertEqual(q['vnp_Amount'], '8500000')
        self.assertEqual(len(created), 14)
        self.assertTrue(vnp.verify_vnpay_response(q))

    def test_expire_is_after_create_by_given_minutes(self):
        """vnp_ExpireDate = CreateDate + expire_minutes."""
        _, _, q = self.build(expire_minutes=30)
        fmt = vnp.VNPAY_DATE_FORMAT
        delta = datetime.strptime(q['vnp_ExpireDate'], fmt) - datetime.strptime(q['vnp_CreateDate'], fmt)
        self.assertEqual(delta.total_seconds(), 1800)

    def test_bank_code_included_only_when_given(self):
        """Có bank_code -> thêm vnp_BankCode, không có thì bỏ."""
        self.assertNotIn('vnp_BankCode', self.build()[2])
        self.assertEqual(self.build(bank_code='NCB')[2]['vnp_BankCode'], 'NCB')

    def test_order_info_truncated_to_255(self):
        """order_info dài 300 ký tự bị cắt còn 255."""
        self.assertEqual(len(self.build(order_info='x' * 300)[2]['vnp_OrderInfo']), 255)

    def test_ip_truncated_to_45(self):
        """IP quá dài bị cắt còn 45 ký tự."""
        self.assertEqual(len(self.build(ip_addr='1' * 60)[2]['vnp_IpAddr']), 45)

    def test_unicode_and_special_chars_in_order_info_roundtrip(self):
        """Tiếng Việt, & và = trong order_info được mã hoá đúng và chữ ký vẫn hợp lệ."""
        _, _, q = self.build(order_info='Đơn #1 & bàn=5')
        self.assertEqual(q['vnp_OrderInfo'], 'Đơn #1 & bàn=5')
        self.assertTrue(vnp.verify_vnpay_response(q))

    def test_zero_amount_is_still_built(self):
        """Biên: amount=0 vẫn dựng URL (nghiệp vụ chặn ở tầng view)."""
        self.assertEqual(self.build(amount=0)[2]['vnp_Amount'], '0')

    def test_large_amount(self):
        """Biên: số tiền lớn 2 tỷ -> nhân 100 không tràn."""
        self.assertEqual(self.build(amount=2_000_000_000)[2]['vnp_Amount'], '200000000000')

    def test_missing_config_raises(self):
        """Thiếu TMN code hoặc secret -> VNPayError."""
        for kw in ({'VNPAY_TMN_CODE': ''}, {'VNPAY_HASH_SECRET_KEY': ''}):
            with override_settings(**kw):
                with self.assertRaises(vnp.VNPayError):
                    vnp.build_vnpay_payment_url(amount=1, order_info='x', txn_ref='r')


@override_settings(**CFG)
class MerchantApiTests(SimpleTestCase):
    def test_query_transaction_posts_signed_payload(self):
        """querydr gửi payload có chữ ký HMAC theo thứ tự trường quy định."""
        with mock.patch.object(vnp.requests, 'post') as post:
            post.return_value.json.return_value = {'vnp_ResponseCode': '00'}
            out = vnp.query_transaction(txn_ref='R', transaction_date='20260101000000', order_info='i')
        payload = post.call_args.kwargs['json']
        fields = [payload[k] for k in ('vnp_RequestId', 'vnp_Version', 'vnp_Command', 'vnp_TmnCode', 'vnp_TxnRef',
                                       'vnp_TransactionDate', 'vnp_CreateDate', 'vnp_IpAddr', 'vnp_OrderInfo')]
        self.assertEqual(payload['vnp_SecureHash'], vnp.hmacsha512('SECRET', '|'.join(fields)))
        self.assertEqual(out, {'vnp_ResponseCode': '00'})

    def test_refund_full_vs_partial_transaction_type(self):
        """Hoàn toàn phần = 02, một phần = 03; amount nhân 100; transaction_no rỗng -> '0'."""
        with mock.patch.object(vnp.requests, 'post') as post:
            post.return_value.json.return_value = {}
            vnp.refund_transaction(txn_ref='R', amount=500, transaction_date='d', transaction_no='', order_info='i',
                                   created_by='ql', full_refund=True)
            full = post.call_args.kwargs['json']
            vnp.refund_transaction(txn_ref='R', amount=500, transaction_date='d', transaction_no='99', order_info='i',
                                   created_by='ql', full_refund=False)
            part = post.call_args.kwargs['json']
        self.assertEqual((full['vnp_TransactionType'], full['vnp_Amount'], full['vnp_TransactionNo']), ('02', '50000', '0'))
        self.assertEqual((part['vnp_TransactionType'], part['vnp_TransactionNo']), ('03', '99'))

    def test_network_error_becomes_vnpay_error(self):
        """Lỗi mạng (RequestException/OSError/ValueError) -> VNPayError, không rò lỗi gốc."""
        for exc in (requests.ConnectionError('x'), OSError('ca'), ValueError('json')):
            with mock.patch.object(vnp.requests, 'post', side_effect=exc):
                with self.assertRaises(vnp.VNPayError):
                    vnp.query_transaction(txn_ref='R', transaction_date='d', order_info='i')

    def test_http_error_becomes_vnpay_error(self):
        """HTTP 500 -> VNPayError."""
        with mock.patch.object(vnp.requests, 'post') as post:
            post.return_value.raise_for_status.side_effect = requests.HTTPError('500')
            with self.assertRaises(vnp.VNPayError):
                vnp.refund_transaction(txn_ref='R', amount=1, transaction_date='d', transaction_no='1',
                                       order_info='i', created_by='u', full_refund=True)
