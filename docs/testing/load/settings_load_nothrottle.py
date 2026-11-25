"""Chỉ dùng cho thử tải: nới throttle khách (cùng 1 IP/bàn) để đo năng lực DB/ASGI. Chạy: DJANGO_SETTINGS_MODULE=settings_load_nothrottle (đặt file trong PYTHONPATH)."""
from backend.settings import *  # noqa
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({k: '1000000/min' for k in ('customer', 'order_create', 'staff_call', 'review', 'table_session')})
