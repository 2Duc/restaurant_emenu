import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

_DEV_KEY = 'dev-only-change-me-before-deploy'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', _DEV_KEY)
DEBUG = os.getenv('DJANGO_DEBUG', '0') == '1'   # an toàn theo mặc định; chạy local: đặt DJANGO_DEBUG=1 trong .env
if not DEBUG and SECRET_KEY == _DEV_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Hãy đặt biến môi trường DJANGO_SECRET_KEY (chuỗi ngẫu nhiên dài) khi chạy DJANGO_DEBUG=0.')
_csv = lambda name, default='': [x.strip() for x in os.getenv(name, default).split(',') if x.strip()]
ALLOWED_HOSTS = _csv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _csv('CSRF_TRUSTED_ORIGINS')
# Railway tự cấp tên miền công khai và dùng host riêng cho health check.
if os.getenv('RAILWAY_PUBLIC_DOMAIN'):
    ALLOWED_HOSTS.append(os.environ['RAILWAY_PUBLIC_DOMAIN'])
    CSRF_TRUSTED_ORIGINS.append('https://' + os.environ['RAILWAY_PUBLIC_DOMAIN'])
if os.getenv('RAILWAY_ENVIRONMENT'):
    ALLOWED_HOSTS.append('healthcheck.railway.app')
# Chạy sau proxy HTTPS (Railway): nhận đúng https để tạo URL tuyệt đối (ảnh món, link VNPay trả về...).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'corsheaders', 'rest_framework', 'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist', 'django_filters', 'channels',
    'api',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # phục vụ file tĩnh (admin, DRF) khi chạy thật
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'backend.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug', 'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

# CSDL: PostgreSQL (theo BRD).
#  - Triển khai (Railway...): đặt DATABASE_URL=postgresql://user:mat_khau@host:port/ten_csdl
#  - Chạy local: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT trong backend/.env
def _database_from_url(url):
    from urllib.parse import urlparse, unquote
    u = urlparse(url)
    if u.scheme == 'sqlite':   # chỉ dùng chạy test nhanh: DATABASE_URL=sqlite:///test.sqlite3
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': u.path.lstrip('/') or ':memory:'}
    return {'ENGINE': 'django.db.backends.postgresql', 'NAME': u.path.lstrip('/'), 'USER': unquote(u.username or ''),
            'PASSWORD': unquote(u.password or ''), 'HOST': u.hostname or 'localhost', 'PORT': str(u.port or 5432), 'CONN_MAX_AGE': 60}


def _apply_pool(cfg):
    """psycopg3 connection pool (Django >= 5.1): mỗi tiến trình tối đa DB_POOL_MAX kết nối; CONN_MAX_AGE=0 để trả kết nối về pool sau request.
    DB_POOL_MAX=0 -> tắt pool. Không áp dụng cho sqlite."""
    if 'sqlite' in cfg['ENGINE']:
        return cfg
    pmax = int(os.getenv('DB_POOL_MAX', '10'))
    if pmax <= 0:
        return cfg
    cfg['CONN_MAX_AGE'] = 0
    cfg.setdefault('OPTIONS', {})['pool'] = {
        'min_size': min(int(os.getenv('DB_POOL_MIN', '2')), pmax), 'max_size': pmax,
        'timeout': float(os.getenv('DB_POOL_TIMEOUT', '30')),
    }
    return cfg


if os.getenv('DATABASE_URL'):
    DATABASES = {'default': _database_from_url(os.environ['DATABASE_URL'])}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': os.getenv('DB_NAME', 'e_menu'),
        'USER': os.getenv('DB_USER', 'postgres'), 'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'), 'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }}
DATABASES['default'] = _apply_pool(DATABASES['default'])

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media')))   # triển khai: trỏ vào Volume bền vững (vd /data/media)
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'api.UserAccount'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'DEFAULT_PARSER_CLASSES': ('api.parsers.ObjectJSONParser', 'rest_framework.parsers.FormParser', 'rest_framework.parsers.MultiPartParser'),
    'EXCEPTION_HANDLER': 'api.exceptions.api_exception_handler',
    # Giới hạn tần suất: login/reauth theo IP; các scope khách (RATE-03) theo bàn (token đã ký), chưa có token thì theo IP.
    'DEFAULT_THROTTLE_RATES': {'login': '10/min', 'reauth': '10/min', 'customer': '120/min', 'order_create': '20/min',
                               'staff_call': '6/min', 'review': '20/min', 'table_session': '30/min'},
    # RATE-01: số reverse proxy tin cậy đứng trước Django (0 = chạy trực tiếp, bỏ qua X-Forwarded-For do client gửi).
    # Railway = 1; sau nginx/ingress 1 tầng = 1. Đặt sai (quá lớn) sẽ cho phép giả IP.
    'NUM_PROXIES': int(os.getenv('NUM_PROXIES', '0')),
}
if not DEBUG:   # XSS-06: không bật Browsable API ở production
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = ('rest_framework.renderers.JSONRenderer',)
if 'test' in sys.argv:   # test: nới giới hạn khách để không chạm trần giữa các test (test throttle tự override_settings)
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({k: '100000/min' for k in ('customer', 'order_create', 'staff_call', 'review', 'table_session')})
# Ghi đè tần suất theo env, vd THROTTLE_RATE_OVERRIDES=table_session=500/min,order_create=200/min (dùng cho chạy test tải/chức năng).
for _pair in _csv('THROTTLE_RATE_OVERRIDES'):
    _scope, _, _rate = _pair.partition('=')
    if _scope.strip() in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] and _rate.strip():
        REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'][_scope.strip()] = _rate.strip()
# CFG-13: HSTS khi chạy HTTPS (Railway có RAILWAY_PUBLIC_DOMAIN => HTTPS); đặt SECURE_HSTS_SECONDS=0 để tắt.
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000' if (not DEBUG and os.getenv('RAILWAY_PUBLIC_DOMAIN')) else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', '0') == '1'
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', '0') == '1'
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id', 'USER_ID_CLAIM': 'user_id',
}
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
CORS_ALLOWED_ORIGIN_REGEXES = _csv('CORS_ALLOWED_ORIGIN_REGEXES')   # vd ^https://.*\.vercel\.app$ cho bản xem trước của Vercel
CORS_ALLOW_CREDENTIALS = True
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + ['x-table-id', 'x-table-token']  # BR-02: token phiên bàn (AUTH-05) gửi kèm mọi yêu cầu của khách; x-table-id chỉ để log
# Cache ngắn cho menu công khai (MENU_CACHE_TTL giây, 0 = tắt): Redis nếu có REDIS_URL, không thì LocMem; test dùng LocMem.
if os.getenv('REDIS_URL') and 'test' not in sys.argv:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': os.environ['REDIS_URL']}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'emenu'}}
MENU_CACHE_TTL = int(os.getenv('MENU_CACHE_TTL', '10'))
if os.getenv('REDIS_URL') and 'test' not in sys.argv:  # test dùng InMemory
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer', 'CONFIG': {
        # brpop_timeout của channels_redis = 5s; redis-py >= 8 mặc định socket_timeout ngắn -> TimeoutError khi WS rảnh. Đặt rõ timeout > 5s.
        'hosts': [{'address': os.getenv('REDIS_URL'), 'socket_timeout': 30, 'socket_connect_timeout': 10,
                   'socket_keepalive': True, 'health_check_interval': 30}]}}}
else:
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

# VNPay sandbox only. Keep all merchant secrets outside source control.
VNPAY_TMN_CODE = os.getenv('VNPAY_TMN_CODE', '')
VNPAY_HASH_SECRET_KEY = os.getenv('VNPAY_HASH_SECRET_KEY', '')
# 'vnpay' = cổng VNPay sandbox thật; 'mock' = cổng giả lập (demo offline). Mặc định: mock nếu thiếu khoá VNPay.
# PAY-02: DEBUG=0 mà không đặt PAYMENT_GATEWAY_MODE -> mặc định 'vnpay' (không tự rơi về mock); thiếu khoá VNPay -> báo lỗi cấu hình.
_gateway_env = os.getenv('PAYMENT_GATEWAY_MODE')
if DEBUG:
    PAYMENT_GATEWAY_MODE = _gateway_env or ('vnpay' if VNPAY_TMN_CODE and VNPAY_HASH_SECRET_KEY else 'mock')
else:
    PAYMENT_GATEWAY_MODE = _gateway_env or 'vnpay'
if PAYMENT_GATEWAY_MODE not in ('vnpay', 'mock'):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('PAYMENT_GATEWAY_MODE chỉ nhận vnpay hoặc mock.')
if not DEBUG and PAYMENT_GATEWAY_MODE == 'vnpay' and not (VNPAY_TMN_CODE and VNPAY_HASH_SECRET_KEY):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('DJANGO_DEBUG=0 cần VNPAY_TMN_CODE và VNPAY_HASH_SECRET_KEY (hoặc đặt rõ PAYMENT_GATEWAY_MODE=mock cho bản demo).')
VNPAY_PAYMENT_URL = os.getenv('VNPAY_PAYMENT_URL', 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html')
VNPAY_RETURN_URL = os.getenv('VNPAY_RETURN_URL', 'http://127.0.0.1:8000/api/payments/vnpay-return/')
FRONTEND_RETURN_URL = os.getenv('FRONTEND_RETURN_URL', 'http://localhost:5173/payment-result')
VNPAY_IPN_URL = os.getenv('VNPAY_IPN_URL', 'http://127.0.0.1:8000/api/payments/vnpay-ipn/')
VNPAY_API_URL = os.getenv('VNPAY_API_URL', 'https://sandbox.vnpayment.vn/merchant_webapi/api/transaction')  # querydr + refund
VNPAY_BANK_CODE = os.getenv('VNPAY_BANK_CODE', '')  # 'VNPAYQR' để mở thẳng trang quét QR của VNPay (nếu merchant sandbox bật)
# Gốc URL frontend dùng dựng link QR của bàn: <FRONTEND_BASE_URL>/table/<id>?k=<qr_token>
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173')
# Địa chỉ ỔN ĐỊNH (tên miền / IP LAN cố định) dùng cho link trong QR in ra; để trống = dùng FRONTEND_BASE_URL.
# QR đã in phụ thuộc địa chỉ này: đổi địa chỉ thì phải in lại.
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '')
