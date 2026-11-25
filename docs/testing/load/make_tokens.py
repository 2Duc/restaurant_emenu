"""Tạo sẵn JWT access token cho waiter/kitchen/manager (tránh đo nhầm throttle login 10/min).

Chạy từ thư mục backend, cùng biến môi trường DB với server thử tải:
  venv/Scripts/python.exe ../docs/testing/load/make_tokens.py ../docs/testing/load/tokens.json
"""
import json, os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from rest_framework_simplejwt.tokens import RefreshToken
from api.models import UserAccount

out = {}
for key, username in [('PV', 'waiter_demo'), ('BEP', 'kitchen_demo'), ('QL', 'manager_demo')]:
    user = UserAccount.objects.get(username=username)
    r = RefreshToken.for_user(user)
    r['role'] = user.role
    out[key] = str(r.access_token)
from api.models import Table
from api.services.table_token import make_table_token
out['TABLES'] = {str(t.id): make_table_token(t) for t in Table.objects.all()}   # X-Table-Token cho khách
json.dump(out, open(sys.argv[1], 'w'))
print('tokens ->', sys.argv[1])
