from rest_framework.exceptions import PermissionDenied

from .table_token import verify_table_token

STAFF_ROLES = ('PV', 'BEP', 'QL', 'AD')
MESSAGE = 'Bạn chỉ thao tác được trong phạm vi bàn của mình. Vui lòng quét lại mã QR của bàn.'


def is_staff(request):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and (user.is_superuser or user.role in STAFF_ROLES))


def customer_table_id(request):
    """Id bàn (chuỗi số) lấy từ header X-Table-Token đã ký; X-Table-Id tự khai KHÔNG còn được tin."""
    token = str(request.META.get('HTTP_X_TABLE_TOKEN', '')).strip()
    cache = getattr(request, '_table_token_cache', None)
    if cache and cache[0] == token:
        return cache[1]
    table_id = verify_table_token(token)
    result = str(table_id) if table_id is not None else None
    try:
        request._table_token_cache = (token, result)
    except AttributeError:
        pass
    return result


def ensure_table_scope(request, table_id):
    """BR-02: khách (không đăng nhập) chỉ thao tác trong bàn mình đang ngồi.

    Frontend gửi header X-Table-Token (đổi từ link QR /table/<id>?k=<mã>); nhân viên đã đăng nhập thì không bị giới hạn.
    """
    if is_staff(request):
        return
    if table_id is None or str(table_id) != customer_table_id(request):
        raise PermissionDenied(MESSAGE)
