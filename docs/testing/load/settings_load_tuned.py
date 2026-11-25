"""Settings chỉ dùng cho thử nghiệm tải (không sửa mã ứng dụng): đóng kết nối DB sau mỗi request (CONN_MAX_AGE=0)."""
from backend.settings import *  # noqa
DATABASES['default']['CONN_MAX_AGE'] = 0
