"""Tích hợp VNPay (sandbox) cho backend Django.

Bám theo dự án mẫu (app/vnpay.py + views.py): dựng URL thanh toán, ký HMAC-SHA512,
kiểm tra chữ ký phản hồi (return/IPN), tra cứu giao dịch (querydr) và hoàn tiền (refund).
"""
import hashlib
import hmac
import urllib.parse
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

VNPAY_DATE_FORMAT = '%Y%m%d%H%M%S'


class VNPayError(RuntimeError):
    pass


def _require_config():
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET_KEY:
        raise VNPayError('Chưa cấu hình VNPAY_TMN_CODE / VNPAY_HASH_SECRET_KEY trong file .env.')


def hmacsha512(key: str, data: str) -> str:
    return hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha512).hexdigest()


def _encoded_pairs(params):
    """Sắp xếp theo key, bỏ giá trị rỗng, encode kiểu quote_plus — dùng cho cả ký lẫn query string."""
    return '&'.join(
        f'{urllib.parse.quote_plus(str(key))}={urllib.parse.quote_plus(str(value))}'
        for key, value in sorted(params.items())
        if value is not None and str(value) != ''
    )


def get_client_ip(request) -> str:
    # Chỉ tin X-Forwarded-For theo số proxy tin cậy (NUM_PROXIES), giống DRF; mặc định 0 = dùng REMOTE_ADDR.
    from rest_framework.settings import api_settings
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    proxies = api_settings.NUM_PROXIES
    if proxies and forwarded:
        addrs = [a.strip() for a in forwarded.split(',') if a.strip()]
        ip = addrs[-min(proxies, len(addrs))] if addrs else ''
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip or '127.0.0.1'


def new_txn_ref(order_id: int) -> str:
    # vnp_TxnRef phải duy nhất mỗi lần gửi sang VNPay, tối đa 100 ký tự.
    return f'ORD{order_id}T{timezone.localtime().strftime("%y%m%d%H%M%S")}{uuid.uuid4().hex[:6]}'


def build_vnpay_payment_url(*, amount: int, order_info: str, txn_ref: str, ip_addr: str = '127.0.0.1',
                            bank_code: str = '', expire_minutes: int = 15):
    """Trả về (pay_url, create_date)."""
    _require_config()
    now = timezone.localtime()
    create_date = now.strftime(VNPAY_DATE_FORMAT)
    params = {
        'vnp_Version': '2.1.0',
        'vnp_Command': 'pay',
        'vnp_TmnCode': settings.VNPAY_TMN_CODE,
        'vnp_Amount': str(int(amount) * 100),
        'vnp_CurrCode': 'VND',
        'vnp_TxnRef': txn_ref,
        'vnp_OrderInfo': order_info[:255],
        'vnp_OrderType': 'other',
        'vnp_Locale': 'vn',
        'vnp_ReturnUrl': settings.VNPAY_RETURN_URL,
        'vnp_IpAddr': ip_addr[:45],
        'vnp_CreateDate': create_date,
        'vnp_ExpireDate': (now + timedelta(minutes=expire_minutes)).strftime(VNPAY_DATE_FORMAT),
    }
    if bank_code:
        params['vnp_BankCode'] = bank_code
    query = _encoded_pairs(params)
    secure_hash = hmacsha512(settings.VNPAY_HASH_SECRET_KEY, query)
    return f'{settings.VNPAY_PAYMENT_URL}?{query}&vnp_SecureHash={secure_hash}', create_date


def verify_vnpay_response(query_dict) -> bool:
    """Kiểm tra vnp_SecureHash của tham số VNPay gửi về (return URL hoặc IPN)."""
    data = {k: v for k, v in dict(query_dict).items() if str(k).startswith('vnp_')}
    secure_hash = data.pop('vnp_SecureHash', None)
    data.pop('vnp_SecureHashType', None)
    if not secure_hash or not settings.VNPAY_HASH_SECRET_KEY:
        return False
    expected = hmacsha512(settings.VNPAY_HASH_SECRET_KEY, _encoded_pairs(data))
    return hmac.compare_digest(expected.lower(), str(secure_hash).lower())


def _post_merchant_api(payload: dict) -> dict:
    try:
        response = requests.post(settings.VNPAY_API_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=20)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, OSError, ValueError) as exc:
        raise VNPayError(f'Không gọi được API VNPay: {exc}') from exc


def query_transaction(*, txn_ref: str, transaction_date: str, order_info: str, ip_addr: str = '127.0.0.1') -> dict:
    """API querydr: tra cứu kết quả giao dịch theo vnp_TxnRef."""
    _require_config()
    request_id = uuid.uuid4().hex
    create_date = timezone.localtime().strftime(VNPAY_DATE_FORMAT)
    fields = [request_id, '2.1.0', 'querydr', settings.VNPAY_TMN_CODE, txn_ref, transaction_date, create_date, ip_addr, order_info]
    payload = {
        'vnp_RequestId': request_id, 'vnp_Version': '2.1.0', 'vnp_Command': 'querydr',
        'vnp_TmnCode': settings.VNPAY_TMN_CODE, 'vnp_TxnRef': txn_ref, 'vnp_OrderInfo': order_info,
        'vnp_TransactionDate': transaction_date, 'vnp_CreateDate': create_date, 'vnp_IpAddr': ip_addr,
        'vnp_SecureHash': hmacsha512(settings.VNPAY_HASH_SECRET_KEY, '|'.join(fields)),
    }
    return _post_merchant_api(payload)


def refund_transaction(*, txn_ref: str, amount: int, transaction_date: str, transaction_no: str,
                       order_info: str, created_by: str, full_refund: bool, ip_addr: str = '127.0.0.1') -> dict:
    """API refund: hoàn tiền toàn phần (02) hoặc một phần (03)."""
    _require_config()
    request_id = uuid.uuid4().hex
    create_date = timezone.localtime().strftime(VNPAY_DATE_FORMAT)
    transaction_type = '02' if full_refund else '03'
    transaction_no = transaction_no or '0'
    fields = [request_id, '2.1.0', 'refund', settings.VNPAY_TMN_CODE, transaction_type, txn_ref,
              str(int(amount) * 100), transaction_no, transaction_date, created_by, create_date, ip_addr, order_info]
    payload = {
        'vnp_RequestId': request_id, 'vnp_Version': '2.1.0', 'vnp_Command': 'refund',
        'vnp_TmnCode': settings.VNPAY_TMN_CODE, 'vnp_TransactionType': transaction_type,
        'vnp_TxnRef': txn_ref, 'vnp_Amount': str(int(amount) * 100), 'vnp_OrderInfo': order_info,
        'vnp_TransactionNo': transaction_no, 'vnp_TransactionDate': transaction_date,
        'vnp_CreateBy': created_by, 'vnp_CreateDate': create_date, 'vnp_IpAddr': ip_addr,
        'vnp_SecureHash': hmacsha512(settings.VNPAY_HASH_SECRET_KEY, '|'.join(fields)),
    }
    return _post_merchant_api(payload)
