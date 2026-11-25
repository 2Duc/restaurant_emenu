"""RATE-03: giới hạn tần suất cho API khách. Khoá theo bàn (token đã ký) để nhiều khách chung wifi quán không đụng nhau;
chưa có token thì theo IP. Nhân viên đã đăng nhập không bị giới hạn ở các throttle này."""
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle

from .services.scope import customer_table_id, is_staff


class CustomerThrottle(SimpleRateThrottle):
    scope = 'customer'

    def get_rate(self):   # đọc lúc gọi (không chốt lúc import) để cấu hình / test đổi được
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        if is_staff(request):
            return None
        table_id = customer_table_id(request)
        ident = f'table-{table_id}' if table_id else self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class OrderCreateThrottle(CustomerThrottle):
    scope = 'order_create'


class StaffCallThrottle(CustomerThrottle):
    scope = 'staff_call'


class ReviewThrottle(CustomerThrottle):
    scope = 'review'


class TableSessionThrottle(CustomerThrottle):
    """Đổi mã QR lấy token: luôn theo IP (chưa có token), chống dò mã k."""
    scope = 'table_session'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}
