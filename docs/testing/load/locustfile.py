"""Locust cho ABC Restaurant QR Menu.

Biến môi trường:
  TOKENS_FILE   đường dẫn tokens.json (make_tokens.py) — nhân viên dùng token tạo sẵn để không dính throttle login 10/min.
  LOGIN_REAL=1  nhân viên đăng nhập thật qua /api/auth/login/ (sẽ bị 429 khi nhiều user cùng IP).
Chạy:
  locust -f locustfile.py --headless -u 100 -r 10 -t 90s --host http://127.0.0.1:8030 --csv out --html out.html
Tỉ lệ user: khách 80%, nhân viên/bếp 15%, quản lý 5%.
"""
import json, os, random
from locust import HttpUser, task, between

TOKENS = {}
if os.getenv('TOKENS_FILE') and os.path.exists(os.getenv('TOKENS_FILE')):
    TOKENS = json.load(open(os.getenv('TOKENS_FILE')))
PASSWORD = os.getenv('SEED_DEMO_PASSWORD', 'Demo@12345')
TABLES = list(range(1, 31))


# LIST_MODE=old: cách FE cũ (Waiter GET /orders/ đầy đủ limit 200, Chef limit 300, quản lý limit 200); new (mặc định): ?active=1 cho PV/Bếp, ?page=1 cho quản lý.
import os as _os
if _os.environ.get('LIST_MODE', 'new') == 'old':
    STAFF_LIST, MANAGER_LIST = '/api/orders/?limit=200', '/api/orders/?limit=200'
else:
    STAFF_LIST, MANAGER_LIST = '/api/orders/?active=1', '/api/orders/?page=1&page_size=20'


class CustomerUser(HttpUser):
    """Khách quét QR tại bàn: xem menu, đặt món, xem đơn, gọi nhân viên."""
    weight = 16
    wait_time = between(1, 3)

    def on_start(self):
        self.table = random.choice(TABLES)
        self.headers = {'X-Table-Token': TOKENS.get('TABLES', {}).get(str(self.table), '')}
        self.order_id = None
        self.menu_ids = []

    @task(5)
    def browse_menu(self):
        with self.client.get('/api/menu-items/', name='GET /api/menu-items/', catch_response=True) as r:
            if r.status_code == 200:
                self.menu_ids = [m['id'] for m in r.json()] or self.menu_ids
            else:
                r.failure(r.status_code)
        self.client.get('/api/categories/', name='GET /api/categories/')

    @task(2)
    def view_table(self):
        self.client.get(f'/api/tables/{self.table}/', headers=self.headers, name='GET /api/tables/[id]/')

    @task(3)
    def place_order(self):
        if not self.menu_ids:
            return
        items = [{'menu_item_id': i, 'quantity': random.randint(1, 3), 'note': 'it cay'}
                 for i in random.sample(self.menu_ids, k=min(2, len(self.menu_ids)))]
        with self.client.post('/api/orders/', json={'table_id': self.table, 'items': items}, headers=self.headers,
                              name='POST /api/orders/', catch_response=True) as r:
            if r.status_code in (200, 201):
                self.order_id = r.json()['id']
            elif r.status_code == 400:
                r.success()   # bàn đang dọn (đúng nghiệp vụ), không tính lỗi
            else:
                r.failure(r.status_code)

    @task(3)
    def view_order(self):
        if self.order_id:
            self.client.get(f'/api/orders/{self.order_id}/', headers=self.headers, name='GET /api/orders/[id]/')

    @task(1)
    def call_staff(self):
        self.client.post('/api/staff-calls/', json={'table': self.table, 'message': 'Cho xin them nuoc'},
                         headers=self.headers, name='POST /api/staff-calls/')


class _StaffBase(HttpUser):
    abstract = True
    wait_time = between(1, 3)
    role = 'PV'
    username = 'waiter_demo'

    def on_start(self):
        token = TOKENS.get(self.role)
        if os.getenv('LOGIN_REAL') == '1' or not token:
            r = self.client.post('/api/auth/login/', json={'username': self.username, 'password': PASSWORD}, name='POST /api/auth/login/')
            token = r.json().get('access') if r.status_code == 200 else None
        self.auth = {'Authorization': f'Bearer {token}'}


class WaiterKitchenUser(_StaffBase):
    """Nhân viên / bếp: list đơn, cập nhật trạng thái món pending->cooking->done->served."""
    weight = 3

    def on_start(self):
        self.role = random.choice(['PV', 'BEP'])
        self.username = 'waiter_demo' if self.role == 'PV' else 'kitchen_demo'
        super().on_start()

    @task(4)
    def list_orders(self):
        self.client.get(STAFF_LIST, headers=self.auth, name='GET /api/orders/ (staff)')

    @task(2)
    def list_calls(self):
        if self.role == 'PV':
            self.client.get('/api/staff-calls/?status=pending', headers=self.auth, name='GET /api/staff-calls/')

    @task(3)
    def advance_item(self):
        r = self.client.get(STAFF_LIST, headers=self.auth, name='GET /api/orders/ (staff)')
        if r.status_code != 200:
            return
        step = {'pending': 'cooking', 'cooking': 'done', 'done': 'served'}
        allowed = {'BEP': ('pending', 'cooking'), 'PV': ('done',)}[self.role]
        data = r.json()
        for order in (data['results'] if isinstance(data, dict) else data):
            for it in order['items']:
                if it['status'] in allowed:
                    with self.client.patch(f"/api/order-items/{it['id']}/status/", json={'status': step[it['status']]},
                                           headers=self.auth, name='PATCH /api/order-items/[id]/status/', catch_response=True) as resp:
                        if resp.status_code in (200, 400):   # 400 = bị người khác chuyển trước (race hợp lệ)
                            resp.success()
                    return


class ManagerUser(_StaffBase):
    weight = 1
    role = 'QL'
    username = 'manager_demo'

    @task(3)
    def report(self):
        self.client.get('/api/reports/summary/?period=month', headers=self.auth, name='GET /api/reports/summary/')

    @task(2)
    def list_orders(self):
        self.client.get(MANAGER_LIST, headers=self.auth, name='GET /api/orders/ (manager)')
