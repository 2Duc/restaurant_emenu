"""AUTH-05: token phiên bàn ký bằng django.core.signing (TimestampSigner), đổi từ link QR (table_id + mã bí mật k)."""
import hashlib
import hmac

from django.core import signing

from ..models import Table

SALT = 'api.table-session'
MAX_AGE_SECONDS = 6 * 60 * 60


def _version(table):
    """Dấu vân tay của mã QR hiện tại: xoay mã QR -> mọi token cũ không còn khớp."""
    return hashlib.sha256(table.qr_token.encode()).hexdigest()[:12]


def _signer():
    return signing.TimestampSigner(salt=SALT)


def check_qr_key(table, key):
    return bool(key) and hmac.compare_digest(str(key).encode(), table.qr_token.encode())


def make_table_token(table):
    return _signer().sign(f'{table.pk}:{_version(table)}')


def verify_table_token(token):
    """Trả về id bàn (int) nếu token hợp lệ, chưa hết hạn và khớp phiên bản mã QR; ngược lại None."""
    if not token or not isinstance(token, str) or len(token) > 300:
        return None
    try:
        raw = _signer().unsign(token, max_age=MAX_AGE_SECONDS)
        table_id, version = raw.split(':', 1)
        table = Table.objects.only('id', 'qr_token').get(pk=int(table_id))
    except (signing.BadSignature, ValueError, Table.DoesNotExist):
        return None
    return table.pk if hmac.compare_digest(version, _version(table)) else None
