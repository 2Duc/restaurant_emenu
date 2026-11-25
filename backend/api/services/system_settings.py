from django.conf import settings

from ..models import Payment, SystemSetting


def method_enabled(cfg: SystemSetting, method: str) -> bool:
    if method == Payment.Method.CASH:
        return cfg.cash_enabled
    if method == Payment.Method.VNPAY:
        return cfg.vnpay_enabled
    if method == Payment.Method.BANK_TRANSFER:
        return cfg.bank_transfer_enabled and cfg.bank_configured   # chưa cấu hình TK nhận thì coi như ẩn
    return False


def mask(value: str) -> str:
    if not value:
        return ''
    return value[:2] + '*' * max(len(value) - 4, 2) + value[-2:] if len(value) > 4 else '*' * len(value)


def public_payload(cfg: SystemSetting) -> dict:
    """Phần khách cần: phương thức đang bật + tài khoản nhận chuyển khoản."""
    data = {
        'methods': {m: method_enabled(cfg, m) for m in ('cash', 'bank_transfer', 'vnpay')},
        'bank': None,
        'invoice_note': cfg.invoice_note,
    }
    if method_enabled(cfg, Payment.Method.BANK_TRANSFER):
        data['bank'] = {'bank_name': cfg.bank_name, 'account_no': cfg.bank_account_no, 'account_name': cfg.bank_account_name}
    return data


def gateway_status() -> dict:
    """Trạng thái cổng thanh toán chỉ đọc từ biến môi trường (không bao giờ trả về khoá bí mật)."""
    return {
        'mode': settings.PAYMENT_GATEWAY_MODE,
        'tmn_code': mask(settings.VNPAY_TMN_CODE),
        'has_hash_secret': bool(settings.VNPAY_HASH_SECRET_KEY),
    }
