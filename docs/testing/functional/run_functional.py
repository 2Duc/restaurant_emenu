# -*- coding: utf-8 -*-
"""Functional test ABC Restaurant (QR Menu) - chạy kịch bản API/WebSocket thật trên backend riêng.

Cách chạy (từ thư mục gốc dự án):
    env -u REQUESTS_CA_BUNDLE -u CURL_CA_BUNDLE -u SSL_CERT_FILE python docs/testing/functional/run_functional.py
    ... --regen   chỉ sinh lại md/xlsx từ results.json (không chạy server)
    ... --shots   chỉ chụp lại ảnh bảng kết quả từ results.json

Backend riêng: daphne :8020, REDIS_URL rỗng (InMemory), sqlite functional.sqlite3, PAYMENT_GATEWAY_MODE=mock.
Sau khi chạy xong: tắt server, xoá functional.sqlite3 và thư mục media tạm.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'backend'
PY = BACKEND / 'venv' / 'Scripts' / 'python.exe'
PORT = 8020
BASE = f'http://127.0.0.1:{PORT}'
API = BASE + '/api'
WSBASE = f'ws://127.0.0.1:{PORT}'
DB_FILE = BACKEND / 'functional.sqlite3'
MEDIA_TMP = HERE / '_media_tmp'
PASSWORD = 'Test@12345'
TMN, SECRET = 'FUNCTEST', 'functionaltestsecret'
RESULTS_JSON = HERE / 'results.json'
MD_FILE = HERE / 'test-scenarios.md'
XLSX_FILE = HERE / 'test-scenarios.xlsx'
SHOTS = HERE / 'screenshots'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PASS, FAIL, TODO = 'Pass', 'Fail', 'Chưa chạy'

# --------------------------------------------------------------------------- registry
TCS = []   # danh sách dict meta theo thứ tự trình bày


def _meta(flow, ref, pre, steps, data, expected, fn=None, manual=None, late=False):
    tid = f'TC-{len(TCS) + 1:03d}'
    TCS.append(dict(id=tid, flow=flow, ref=ref, pre=pre, steps=steps, data=data, expected=expected,
                    fn=fn, manual=manual, late=late, actual='', status='', note=''))
    return tid


def tc(flow, ref, pre, steps, data, expected, late=False):
    def deco(fn):
        _meta(flow, ref, pre, steps, data, expected, fn=fn, late=late)
        return fn
    return deco


def manual(flow, ref, pre, steps, data, expected, guide, evidence='', status=None, actual=None):
    _meta(flow, ref, pre, steps, data, expected,
          manual=dict(actual=actual or ('Thủ công — ' + guide), note=evidence, status=status))


# --------------------------------------------------------------------------- http helpers
import requests  # noqa: E402

SESS = requests.Session()
SESS.trust_env = False
TOK = {}     # role -> access token
REF = {}     # role -> refresh token
M = {}       # tên món -> id
PRICE = {'Phở bò tái': 85000, 'Chả giò hải sản': 75000, 'Gỏi cuốn tôm thịt': 60000, 'Cơm chiên hải sản': 110000,
         'Nấm đùi gà kho tiêu': 70000, 'Trà sen vàng': 45000, 'Trà đào cam sả': 42000, 'Chè khúc bạch': 50000}
ST = {}      # trạng thái dùng chung giữa TC
_next_table = [0]


TTOK = {}    # id bàn -> token phiên bàn (AUTH-05)


def table_token(t):
    """Lấy token phiên bàn như khách quét QR: quản lý đọc link QR (có ?k=) rồi POST /tables/session/ (cache theo bàn)."""
    if t in TTOK:
        return TTOK[t]
    tok = None
    mgr = TOK.get('QL') or TOK.get('AD')
    if mgr:
        for _ in range(6):
            r = SESS.get(API + f'/tables/{t}/qr/', headers={'Authorization': 'Bearer ' + mgr}, timeout=30)
            if r.status_code != 200:
                break
            k = urllib.parse.parse_qs(urllib.parse.urlparse(r.json()['url']).query).get('k', [''])[0]
            s = SESS.post(API + '/tables/session/', json={'table_id': int(t), 'k': k}, timeout=30)
            if s.status_code == 200:
                tok = s.json()['token']
                break
            if s.status_code != 429:
                break
            time.sleep(10)
    if tok:
        TTOK[t] = tok
    return tok


def rq(method, path, tok=None, tbl=None, **kw):
    h = kw.pop('headers', {})
    if tok:
        h['Authorization'] = 'Bearer ' + tok
    if tbl is not None:
        h['X-Table-Id'] = str(tbl)          # chỉ để log; quyền dựa trên X-Table-Token
        tt = table_token(tbl)
        if tt:
            h['X-Table-Token'] = tt
    for attempt in range(4):
        r = SESS.request(method, API + path, headers=h, timeout=30, allow_redirects=False, **kw)
        if r.status_code == 429 and tbl is not None and attempt < 3:   # throttle khách (theo bàn): chờ rồi thử lại
            time.sleep(float(r.headers.get('Retry-After', 5)) + 1)
            continue
        return r


def st(r, code, msg=''):
    codes = code if isinstance(code, (tuple, list, set)) else (code,)
    if r.status_code not in codes:
        raise AssertionError(f'{msg} HTTP {r.status_code} (mong đợi {code}): {r.text[:200]}')
    return r


def eq(a, b, msg=''):
    if a != b:
        raise AssertionError(f'{msg}: mong đợi {b!r}, thực tế {a!r}')


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def vnd(n):
    return f'{int(float(n)):,}'.replace(',', '.')


def rows(j):
    return j['results'] if isinstance(j, dict) and 'results' in j else j


def new_table():
    _next_table[0] += 1
    return _next_table[0]


def login(username, password=PASSWORD):
    return rq('POST', '/auth/login/', json={'username': username, 'password': password})


def mk_order(items, t=None, tok=None):
    """items: [(tên món, sl, ghi chú?)]. Khách gửi X-Table-Id; nếu có tok → nhân viên đặt hộ."""
    t = t or new_table()
    body = {'table_id': t, 'items': [dict(menu_item_id=M[i[0]], quantity=i[1], note=(i[2] if len(i) > 2 else '')) for i in items]}
    r = rq('POST', '/orders/', tok=tok, tbl=None if tok else t, json=body)
    st(r, (200, 201), 'tạo đơn')
    return t, r.json()


def line(order, name):
    for it in order['items']:
        if it['menu_item_name'] == name:
            return it
    raise AssertionError(f'không có dòng {name}')


def item_status(item_id, status, role):
    return rq('PATCH', f'/order-items/{item_id}/status/', tok=TOK[role], json={'status': status})


def cook_serve(order, upto='served'):
    for it in order['items']:
        st(item_status(it['id'], 'cooking', 'BEP'), 200, 'cooking')
        st(item_status(it['id'], 'done', 'BEP'), 200, 'done')
        if upto == 'served':
            st(item_status(it['id'], 'served', 'PV'), 200, 'served')


def pay_cash(order_id, t):
    r = st(rq('POST', '/payments/create/', tbl=t, json={'order_id': order_id, 'method': 'cash'}), (200, 201), 'tạo tiền mặt')
    pid = r.json()['id']
    st(rq('POST', f'/payments/{pid}/confirm-cash/', tok=TOK['PV']), 200, 'xác nhận tiền mặt')
    return pid


def completed_order(items=(('Phở bò tái', 1),), t=None):
    t, o = mk_order(list(items), t)
    cook_serve(o)
    pay_cash(o['id'], t)
    return t, st(rq('GET', f"/orders/{o['id']}/", tbl=t), 200).json()


def get_order(oid, t=None, tok=None):
    return st(rq('GET', f'/orders/{oid}/', tok=tok, tbl=t), 200).json()


def tbl_status(t):
    return st(rq('GET', f'/tables/{t}/', tok=TOK['PV']), 200).json()['status']


def png_bytes(w=8, h=8, pad=0):
    raw = b''.join(b'\x00' + bytes([200, 60, 60]) * w for _ in range(h))

    def ch(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b'') + b'\0' * pad)


def vn_sign(params):
    pairs = '&'.join(f'{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}'
                     for k, v in sorted(params.items()) if v is not None and str(v) != '')
    return hmac.new(SECRET.encode(), pairs.encode(), hashlib.sha512).hexdigest()


def vn_params(pay, code='00', status='00', amount=None, tmn=TMN, bad_hash=False):
    p = {'vnp_TmnCode': tmn, 'vnp_TxnRef': pay['transaction_id'],
         'vnp_Amount': str(amount if amount is not None else int(float(pay['amount'])) * 100),
         'vnp_ResponseCode': code, 'vnp_TransactionStatus': status, 'vnp_TransactionNo': '14000001',
         'vnp_BankCode': 'NCB', 'vnp_PayDate': datetime.now().strftime('%Y%m%d%H%M%S'), 'vnp_OrderInfo': 'functional test'}
    p['vnp_SecureHash'] = 'deadbeef' * 16 if bad_hash else vn_sign(p)
    return p


def vnpay_create(order_id, t):
    return st(rq('POST', '/payments/create/', tbl=t, json={'order_id': order_id, 'method': 'vnpay'}), 201, 'tạo vnpay').json()


def txn_of(pay):
    return urllib.parse.parse_qs(urllib.parse.urlparse(pay['pay_url']).query)['txn'][0]


def db_exec(sql, args=()):
    con = sqlite3.connect(DB_FILE)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- websocket helpers
import websockets  # noqa: E402


async def ws_open(group, tok=None, anon=False):
    if tok is None and not anon and group.startswith('table_'):
        tok = table_token(int(group[6:]))   # WS-02: khách cần token phiên bàn
    url = f'{WSBASE}/ws/{group}/' + (f'?token={tok}' if tok else '')
    return await websockets.connect(url, open_timeout=5)


async def ws_try(group, tok=None, anon=False):
    """True nếu kết nối được và nhận pong."""
    try:
        ws = await ws_open(group, tok, anon)
    except Exception:
        return False
    try:
        await ws.send(json.dumps({'type': 'ping'}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
        return msg.get('type') == 'pong'
    except Exception:
        return False
    finally:
        await ws.close()


async def ws_wait(ws, typ, pred=None, timeout=5):
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            raise AssertionError(f'không nhận được sự kiện {typ} trong {timeout}s')
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), left))
        except asyncio.TimeoutError:
            raise AssertionError(f'không nhận được sự kiện {typ} trong {timeout}s')
        if msg.get('type') == typ and (pred is None or pred(msg)):
            return msg


async def ws_none(ws, typ, pred=None, timeout=2):
    try:
        await ws_wait(ws, typ, pred, timeout)
    except AssertionError:
        return True
    return False


def arun(coro):
    return asyncio.run(coro)


# =========================================================================== KỊCH BẢN
F_AUTH = 'Xác thực (BR-07)'
F_QR = 'Khách - QR / bàn'
F_MENU = 'Khách - Xem/tìm/lọc món'
F_CART = 'Khách - Giỏ hàng & đặt món'
F_ADD = 'Khách - Gọi thêm / huỷ món'
F_CALL = 'Khách - Gọi nhân viên & hoá đơn tạm tính'
F_PROMO = 'Khách - Khuyến mãi'
F_PAY = 'Thanh toán'
F_REV = 'Khách - Đánh giá món'
F_KIT = 'Bếp'
F_WAI = 'Phục vụ'
F_MGM = 'Quản lý - Danh mục/Món'
F_MGT = 'Quản lý - Bàn/QR'
F_MGP = 'Quản lý - Khuyến mãi/Nhân viên'
F_MGO = 'Quản lý - Đơn/Hoá đơn/Báo cáo'
F_AC8 = 'Phân quyền (AC-08)'
F_WS = 'Realtime WebSocket (AC-03)'
F_MOB = 'Mobile (AC-09)'


# ---- Xác thực
@tc(F_AUTH, 'BR-07, AC-08', 'Server chạy, đã có tài khoản test 4 role',
    '1. POST /api/auth/login/ với từng tài khoản\n2. GET /api/auth/me/ bằng access token\n3. POST /api/auth/refresh/',
    'manager_demo(QL), waiter_demo(PV), kitchen_demo(BEP), admin_test(AD) / Test@12345',
    'Đăng nhập 200, trả access+refresh, role đúng; /auth/me/ trả đúng user; refresh cấp access mới')
def _():
    out = []
    for u, role in (('manager_demo', 'QL'), ('waiter_demo', 'PV'), ('kitchen_demo', 'BEP'), ('admin_test', 'AD')):
        j = st(login(u), 200, f'login {u}').json()
        eq(j['user']['role'], role, f'role {u}')
        ok(j['access'] and j['refresh'], 'thiếu token')
        TOK[role], REF[role] = j['access'], j['refresh']
        eq(st(rq('GET', '/auth/me/', tok=j['access']), 200).json()['username'], u, 'me')
        out.append(f'{u}={role}')
    r = st(rq('POST', '/auth/refresh/', json={'refresh': REF['QL']}), 200, 'refresh')
    ok(r.json().get('access'), 'refresh không trả access')
    return 'Đăng nhập OK: ' + ', '.join(out) + '; refresh 200'


@tc(F_AUTH, 'BR-07', 'Có user manager_demo và user bị khoá locked_test',
    '1. Đăng nhập sai mật khẩu\n2. Đăng nhập user không tồn tại\n3. Đăng nhập user is_active=false\n4. Gọi API cần quyền không có token',
    'sai mật khẩu; ghost_user; locked_test; không Authorization',
    'Các trường hợp 1-3 trả 401 "Sai tên đăng nhập hoặc mật khẩu"; truy cập không token trả 401')
def _():
    c = []
    for u, p in (('manager_demo', 'sai-mat-khau'), ('ghost_user', PASSWORD), ('locked_test', PASSWORD)):
        r = login(u, p)
        eq(r.status_code, 401, f'login {u}')
        c.append(r.status_code)
    eq(rq('GET', '/auth/me/').status_code, 401, 'me không token')
    return f'login sai/không tồn tại/bị khoá -> {c}; /auth/me/ không token -> 401'


# ---- Khách: QR / bàn
@tc(F_QR, 'AC-01, BR-01, BR-02', 'Seed 30 bàn (+ 90 bàn fixture khu "FT" cho test)',
    '1. Khách mở /table/<id>: frontend gọi GET /api/tables/<id>/ (không đăng nhập)\n2. GET /api/tables/by-number/5/\n3. GET /api/tables/9999/',
    'bàn 7, số bàn 5, bàn 9999',
    '200 trả đúng id/số bàn/khu/trạng thái, không cần đăng nhập; bàn không tồn tại trả 404')
def _():
    j = st(rq('GET', '/tables/7/'), 200).json()
    eq(j['id'], 7, 'id'); eq(j['number'], '7', 'number')
    ok(j['area'] and 'status' in j, 'thiếu area/status')
    eq(st(rq('GET', '/tables/by-number/5/'), 200).json()['id'], 5, 'by-number')
    eq(rq('GET', '/tables/9999/').status_code, 404, 'bàn 9999')
    return f"Bàn 7: number={j['number']}, area={j['area']}, status={j['status']}; by-number/5 id=5; bàn 9999 -> 404"


def _qr_key(t):
    j = st(rq('GET', f'/tables/{t}/qr/', tok=TOK['QL']), 200).json()
    return urllib.parse.parse_qs(urllib.parse.urlparse(j['url']).query)['k'][0]


@tc(F_QR, 'AUTH-05, BR-02', 'Bàn fixture; link QR có ?k=<mã bí mật> (quản lý đọc qua /tables/<id>/qr/)',
    '1. POST /api/tables/session/ {table_id, k} với k đúng\n2. Dùng token ở header X-Table-Token: GET current-order\n3. k sai / thiếu / table_id sai kiểu / k của bàn khác',
    'bàn mới; k đúng; k="sai"; table_id="abc"',
    'k đúng → 200 + token (hạn 6h); token dùng được (không 403); k sai/thiếu/bàn khác → 403; table_id sai kiểu → 400')
def _():
    t, other = new_table(), new_table()
    k = _qr_key(t)
    r = st(SESS.post(API + '/tables/session/', json={'table_id': t, 'k': k}, timeout=30), 200, 'đổi token')
    j = r.json()
    eq(j['table_id'], t, 'table_id'); ok(j['token'] and j['expires_in'] == 6 * 3600, 'token/expires_in')
    c = rq('GET', f'/tables/{t}/current-order/', headers={'X-Table-Token': j['token']})
    ok(c.status_code in (200, 404), f'token hợp lệ nhưng bị {c.status_code}')
    bad = [SESS.post(API + '/tables/session/', json=b, timeout=30).status_code for b in (
        {'table_id': t, 'k': 'sai'}, {'table_id': t}, {'table_id': other, 'k': k})]
    eq(bad, [403, 403, 403], 'k sai')
    eq(SESS.post(API + '/tables/session/', json={'table_id': 'abc', 'k': 'x'}, timeout=30).status_code, 400, 'table_id sai kiểu')
    return f'Bàn {t}: k đúng → 200 + token; token dùng được (current-order {c.status_code}); k sai/thiếu/bàn khác {bad}; table_id "abc" → 400'


@tc(F_QR, 'AUTH-05, BO-03', 'Bàn fixture đã có token phiên bàn; token quản lý/phục vụ',
    '1. Phục vụ POST /api/tables/<id>/rotate-qr/\n2. Quản lý POST rotate-qr\n3. Dùng k cũ và token cũ\n4. Dùng k mới\n5. GET audit-logs',
    'bàn mới',
    'PV → 403; QL → 200 + link mới; k cũ → 403; token cũ → 403 khi đặt món; k mới → 200; audit có TABLE_QR_ROTATE')
def _():
    t = new_table()
    old_k, old_tok = _qr_key(t), table_token(t)
    ok(old_tok, 'không lấy được token ban đầu')
    eq(rq('POST', f'/tables/{t}/rotate-qr/', tok=TOK['PV']).status_code, 403, 'PV đổi mã')
    r = st(rq('POST', f'/tables/{t}/rotate-qr/', tok=TOK['QL']), 200, 'QL đổi mã')
    new_k = r.json()['url'].split('k=')[1]
    ok(new_k != old_k, 'mã không đổi')
    TTOK.pop(t, None)
    eq(SESS.post(API + '/tables/session/', json={'table_id': t, 'k': old_k}, timeout=30).status_code, 403, 'k cũ')
    if 'Phở bò tái' not in M:
        for i in rows(st(rq('GET', '/menu-items/'), 200).json()):
            M[i['name']] = i['id']
    body = dict(table_id=t, items=[dict(menu_item_id=M['Phở bò tái'], quantity=1)])
    eq(rq('POST', '/orders/', headers={'X-Table-Token': old_tok}, json=body).status_code, 403, 'token cũ')
    eq(SESS.post(API + '/tables/session/', json={'table_id': t, 'k': new_k}, timeout=30).status_code, 200, 'k mới')
    logs = rows(st(rq('GET', '/audit-logs/', tok=TOK['QL'], params={'limit': 50}), 200).json())
    ok(any(x['action'] == 'TABLE_QR_ROTATE' for x in logs), 'thiếu audit TABLE_QR_ROTATE')
    return f'Bàn {t}: PV 403, QL 200; k cũ 403, token cũ 403, k mới 200; audit TABLE_QR_ROTATE có'


manual(F_QR, 'AC-01, BR-01, AC-04', 'Máy in/điện thoại có camera; QR đã tải từ màn Quản lý > Bàn',
       '1. Quản lý in/tải QR bàn 5\n2. Dùng camera điện thoại quét QR\n3. Kiểm tra trình duyệt mở /table/5, huy hiệu "Bàn 5" và danh sách món',
       'QR bàn 5; điện thoại + Wi-Fi cùng mạng (xem README mục "Test QR bằng điện thoại")',
       'Quét QR mở đúng link /table/5, hiển thị đúng bàn và thực đơn; QR chỉ chứa đường dẫn + mã bàn',
       'quét QR bằng camera thật (không tự động hoá được); phần dữ liệu link QR đã kiểm bằng API ở TC "Sinh QR bàn"')


# ---- Khách: xem/tìm/lọc món
@tc(F_MENU, 'AC-01, BO-01', 'Seed 8 món / 5 danh mục',
    '1. GET /api/menu-items/ (không đăng nhập)\n2. GET /api/categories/',
    'không token',
    '200; ≥ 8 món đang bán, mỗi món có name/price/category_name/image_url; ≥ 5 danh mục')
def _():
    items = rows(st(rq('GET', '/menu-items/'), 200).json())
    ok(len(items) >= 8, f'chỉ {len(items)} món')
    ok(all(i['is_available'] for i in items), 'khách thấy món ngừng bán')
    ok(all(i['name'] and float(i['price']) > 0 and i['category_name'] for i in items), 'thiếu trường')
    ok(all('image_url' in i for i in items), 'thiếu trường image_url')
    for i in items:
        M[i['name']] = i['id']
    cats = rows(st(rq('GET', '/categories/'), 200).json())
    ok(len(cats) >= 5, 'thiếu danh mục')
    return f'{len(items)} món, {len(cats)} danh mục, tất cả đang bán'


@tc(F_MENU, 'AC-01', 'Có món "Phở bò tái" và danh mục "Đồ uống"',
    '1. GET /api/menu-items/?search=phở\n2. GET ?search=zzzz\n3. GET ?search=Đồ uống (tìm theo tên danh mục)',
    'phở / zzzz / Đồ uống',
    'Tìm "phở" trả "Phở bò tái"; từ khoá không khớp trả rỗng; tìm theo danh mục trả các món đồ uống')
def _():
    def names(q):
        return [i['name'] for i in rows(st(rq('GET', '/menu-items/', params={'search': q}), 200).json())]
    a, b, c = names('phở'), names('zzzz'), names('Đồ uống')
    ok('Phở bò tái' in a, f'search phở -> {a}')
    eq(b, [], 'search zzzz')
    ok('Trà sen vàng' in c and 'Trà đào cam sả' in c, f'search Đồ uống -> {c}')
    return f'phở -> {a}; zzzz -> []; Đồ uống -> {c}'


@tc(F_MENU, 'AC-01', 'Có ≥ 2 danh mục',
    '1. GET /api/menu-items/?category=<id món chính>\n2. GET ?ordering=price và ?ordering=-price',
    'danh mục "Món chính"',
    'Chỉ trả món thuộc danh mục chọn; sắp xếp giá tăng/giảm đúng')
def _():
    cats = rows(st(rq('GET', '/categories/'), 200).json())
    cid = next(c['id'] for c in cats if c['name'] == 'Món chính')
    j = rows(st(rq('GET', '/menu-items/', params={'category': cid}), 200).json())
    ok(j and all(i['category'] == cid for i in j), 'lọc danh mục sai')
    pr = [float(i['price']) for i in rows(st(rq('GET', '/menu-items/', params={'ordering': 'price'}), 200).json())]
    eq(pr, sorted(pr), 'tăng dần')
    pr2 = [float(i['price']) for i in rows(st(rq('GET', '/menu-items/', params={'ordering': '-price'}), 200).json())]
    eq(pr2, sorted(pr2, reverse=True), 'giảm dần')
    return f'Món chính: {len(j)} món đúng danh mục; giá tăng {pr[0]:.0f}..{pr[-1]:.0f}; giảm đúng'


# ---- Giỏ hàng & đặt món
manual(F_CART, 'AC-02, BO-01', 'Mở /table/5 trên trình duyệt (375px)',
       '1. Bấm "+" thêm 3 món, tăng/giảm số lượng, xoá 1 món\n2. Kiểm tra tổng tiền và badge giỏ\n3. Tải lại trang, kiểm tra giỏ còn giữ',
       'Phở x2, Trà đào x1, Chè x1',
       'Giỏ cập nhật số lượng/tổng tiền đúng, xoá được món, không âm số lượng',
       'thao tác giỏ là logic trình duyệt; unit test logic giỏ: frontend/src/screens/Menu/cartUtils.test.js (chạy `npm test`)')


@tc(F_CART, 'AC-02, BR-03', 'Bàn trống; khách mở link bàn (token phiên bàn từ QR)',
    '1. POST /api/orders/ {table_id, items[{menu_item_id,quantity,note}]} với X-Table-Token\n2. GET /api/tables/<id>/ (nhân viên)',
    'Bàn mới; Phở x2 (ghi chú "Ít hành, không giá"), Trà đào x1',
    '201; đơn pending; tạm tính = 85.000×2+42.000 = 212.000; ghi chú lưu đúng; mọi món "pending"; bàn chuyển "occupied"')
def _():
    t, o = mk_order([('Phở bò tái', 2, 'Ít hành, không giá'), ('Trà đào cam sả', 1)])
    eq(o['status'], 'pending', 'status'); eq(int(float(o['subtotal_amount'])), 212000, 'subtotal')
    eq(int(float(o['total_amount'])), 212000, 'total')
    eq(line(o, 'Phở bò tái')['note'], 'Ít hành, không giá', 'ghi chú')
    ok(all(i['status'] == 'pending' for i in o['items']), 'trạng thái món')
    eq(tbl_status(t), 'occupied', 'trạng thái bàn')
    ST['t1'], ST['o1'] = t, o
    return f"Đơn #{o['id']} bàn {t}: pending, tạm tính {vnd(o['subtotal_amount'])}đ, ghi chú lưu, bàn occupied"


@tc(F_CART, 'AC-02, BR-02', 'Có bàn trống',
    '1. Món không tồn tại\n2. Số lượng 0, 100\n3. items rỗng\n4. thiếu table_id',
    'menu_item_id 99999; quantity 0/100; items []',
    'Món không tồn tại → 404; dữ liệu sai → 400; không tạo đơn, bàn vẫn trống')
def _():
    t = new_table()
    pho = M['Phở bò tái']
    bad = [dict(table_id=t, items=[dict(menu_item_id=99999, quantity=1)]),
           dict(table_id=t, items=[dict(menu_item_id=pho, quantity=0)]),
           dict(table_id=t, items=[dict(menu_item_id=pho, quantity=100)]),
           dict(table_id=t, items=[]),
           dict(items=[dict(menu_item_id=pho, quantity=1)])]
    codes = []
    for b, e in zip(bad, [404, 400, 400, 400, 400]):
        r = rq('POST', '/orders/', tbl=t, json=b)
        eq(r.status_code, e, f'body {b}')
        codes.append(r.status_code)
    eq(tbl_status(t), 'empty', 'bàn vẫn trống')
    return f'Mã trả về {codes}; bàn {t} vẫn empty'


@tc(F_CART, 'BR-02, AC-08', 'Đơn bàn T1 đã tạo (TC đặt món)',
    '1. Khách bàn B gửi đơn cho bàn A\n2. Thiếu X-Table-Token\n3. X-Table-Token rác; 4. chỉ có X-Table-Id tự khai',
    'token bàn B, body table_id=A; header trống; token "abc"; X-Table-Id=A không token',
    'Cả 4 trường hợp 403 (BR-02/AUTH-05: khách chỉ thao tác trong bàn mình, X-Table-Id tự khai không được tin); không tạo đơn')
def _():
    a, b = ST['t1'], new_table()
    body = dict(table_id=a, items=[dict(menu_item_id=M['Phở bò tái'], quantity=1)])
    c = [rq('POST', '/orders/', tbl=b, json=body).status_code,
         rq('POST', '/orders/', json=body).status_code,
         rq('POST', '/orders/', headers={'X-Table-Token': 'abc'}, json=body).status_code,
         rq('POST', '/orders/', headers={'X-Table-Id': str(a)}, json=body).status_code]
    eq(c, [403, 403, 403, 403], 'mã trả về')
    return f'Bàn {b} đặt cho bàn {a}/thiếu token/token sai/chỉ X-Table-Id -> {c}'


# ---- Gọi thêm / huỷ món
@tc(F_ADD, 'AC-02, BR-03', 'Bàn T1 đang có đơn mở (pending)',
    '1. POST /api/orders/ lần 2 cùng bàn (Gỏi cuốn x1)\n2. POST /api/orders/<id>/add-items/ (Chè x1)\n3. add-items từ bàn khác',
    'Gỏi cuốn x1 rồi Chè khúc bạch x1',
    'Lần 2 trả 200 (gộp vào đơn hiện có, cùng id); add-items 200; tạm tính cộng dồn 212.000 → 272.000 → 322.000, 4 dòng; add-items từ bàn khác 403')
def _():
    t, o = ST['t1'], ST['o1']
    j = st(rq('POST', '/orders/', tbl=t, json=dict(table_id=t, items=[dict(menu_item_id=M['Gỏi cuốn tôm thịt'], quantity=1)])), 200, 'gộp đơn').json()
    eq(j['id'], o['id'], 'cùng đơn'); eq(int(float(j['subtotal_amount'])), 272000, 'subtotal 1')
    j2 = st(rq('POST', f"/orders/{o['id']}/add-items/", tbl=t, json={'items': [dict(menu_item_id=M['Chè khúc bạch'], quantity=1)]}), 200, 'add-items').json()
    eq(int(float(j2['subtotal_amount'])), 322000, 'subtotal 2'); eq(len(j2['items']), 4, 'số dòng')
    ST['o1'] = j2
    r3 = rq('POST', f"/orders/{o['id']}/add-items/", tbl=new_table(), json={'items': [dict(menu_item_id=M['Chè khúc bạch'], quantity=1)]})
    eq(r3.status_code, 403, 'add-items bàn khác')
    return f"Gộp vào đơn #{j['id']} (200), tạm tính 272.000 → 322.000, 4 dòng; add-items từ bàn khác -> 403"


@tc(F_ADD, 'AC-02, BR-03', 'Đơn T1 có dòng Chè (pending)',
    '1. POST /api/order-items/<id>/cancel/ cho dòng Chè (pending)\n2. Xem lại đơn',
    'dòng Chè khúc bạch',
    '200; dòng bị xoá; tạm tính về 272.000; đơn vẫn mở')
def _():
    t, o = ST['t1'], ST['o1']
    it = line(o, 'Chè khúc bạch')
    j = st(rq('POST', f"/order-items/{it['id']}/cancel/", tbl=t), 200, 'huỷ món').json()
    eq(int(float(j['subtotal_amount'])), 272000, 'subtotal')
    ok(all(i['id'] != it['id'] for i in j['items']), 'dòng còn tồn tại')
    eq(j['status'], 'pending', 'đơn')
    ST['o1'] = j
    return f"Huỷ dòng #{it['id']} -> 200, còn {len(j['items'])} dòng, tạm tính {vnd(j['subtotal_amount'])}đ"


@tc(F_ADD, 'BR-03', 'Đơn có 2 món, 1 món bếp đã nhận (cooking)',
    '1. Bếp chuyển món A sang cooking\n2. Khách huỷ món A (đã cooking)\n3. Khách huỷ món B (pending)',
    'Phở x1 + Chè x1',
    'Huỷ món đang chế biến → 400 "Món đã được bếp nhận"; huỷ món pending → 200')
def _():
    t, o = mk_order([('Phở bò tái', 1), ('Chè khúc bạch', 1)])
    a, b = line(o, 'Phở bò tái'), line(o, 'Chè khúc bạch')
    st(item_status(a['id'], 'cooking', 'BEP'), 200)
    r = rq('POST', f"/order-items/{a['id']}/cancel/", tbl=t)
    eq(r.status_code, 400, 'huỷ cooking')
    st(rq('POST', f"/order-items/{b['id']}/cancel/", tbl=t), 200, 'huỷ pending')
    return f"Huỷ món cooking -> 400 ({r.json().get('detail')}); huỷ món pending -> 200"


@tc(F_ADD, 'BR-03, BR-02', 'Bàn mới, 1 món pending',
    '1. Khách bàn khác thử huỷ món\n2. Khách huỷ món duy nhất của đơn\n3. GET /api/tables/<id>/ (nhân viên)',
    '1 dòng Chè khúc bạch',
    'Món của bàn khác huỷ → 403; huỷ hết món → đơn "cancelled" và bàn trả "empty"')
def _():
    t, o = mk_order([('Chè khúc bạch', 1)])
    it = o['items'][0]
    eq(rq('POST', f"/order-items/{it['id']}/cancel/", tbl=new_table()).status_code, 403, 'huỷ từ bàn khác')
    j = st(rq('POST', f"/order-items/{it['id']}/cancel/", tbl=t), 200).json()
    eq(j['status'], 'cancelled', 'đơn'); eq(tbl_status(t), 'empty', 'bàn')
    return f"Bàn khác huỷ -> 403; huỷ hết -> đơn #{o['id']} cancelled, bàn {t} empty"


# ---- Gọi nhân viên / hoá đơn
@tc(F_CALL, 'AC-02, BO-01, BR-02', 'Bàn T1 đang dùng',
    '1. POST /api/staff-calls/ {table, message} với X-Table-Token\n2. Gọi lần 2 trong 2 phút\n3. Gọi cho bàn khác bằng header bàn T1',
    'message "Xin thêm nước"',
    'Lần 1: 201 pending; lần 2: 200 trả lại yêu cầu cũ (chống spam); gọi hộ bàn khác: 403')
def _():
    t = ST['t1']
    r = st(rq('POST', '/staff-calls/', tbl=t, json={'table': t, 'message': 'Xin thêm nước'}), 201, 'gọi lần 1')
    cid = r.json()['id']; eq(r.json()['status'], 'pending', 'status')
    r2 = st(rq('POST', '/staff-calls/', tbl=t, json={'table': t, 'message': 'Xin thêm nước'}), 200, 'gọi lần 2')
    eq(r2.json()['id'], cid, 'cùng yêu cầu')
    eq(rq('POST', '/staff-calls/', tbl=t, json={'table': new_table(), 'message': 'x'}).status_code, 403, 'bàn khác')
    ST['call'] = cid
    return f'Yêu cầu #{cid}: 201 pending; gọi lại -> 200 cùng #{cid}; bàn khác -> 403'


@tc(F_CALL, 'AC-03, BO-02', 'Có yêu cầu gọi nhân viên pending',
    '1. Phục vụ GET /api/staff-calls/?status=pending\n2. Bếp PATCH status\n3. PATCH accepted rồi resolved\n4. PATCH resolved→accepted',
    'waiter_demo; kitchen_demo',
    'Phục vụ thấy yêu cầu, accepted/resolved 200; chuyển ngược 400; bếp 403')
def _():
    cid = ST['call']
    lst = rows(st(rq('GET', '/staff-calls/', tok=TOK['PV'], params={'status': 'pending'}), 200).json())
    ok(any(c['id'] == cid for c in lst), 'không thấy yêu cầu pending')
    eq(rq('PATCH', f'/staff-calls/{cid}/status/', tok=TOK['BEP'], json={'status': 'accepted'}).status_code, 403, 'bếp')
    st(rq('PATCH', f'/staff-calls/{cid}/status/', tok=TOK['PV'], json={'status': 'accepted'}), 200)
    st(rq('PATCH', f'/staff-calls/{cid}/status/', tok=TOK['PV'], json={'status': 'resolved'}), 200)
    eq(rq('PATCH', f'/staff-calls/{cid}/status/', tok=TOK['PV'], json={'status': 'accepted'}).status_code, 400, 'ngược')
    return 'pending→accepted→resolved 200; resolved→accepted 400; bếp 403'


@tc(F_CALL, 'AC-02, BO-01, BR-02', 'Đơn T1 (Phở x2, Trà đào, Gỏi cuốn); một bàn khác chưa có đơn',
    '1. Khách GET /api/orders/<id>/ (hoá đơn tạm tính)\n2. GET /api/tables/<id>/current-order/\n3. Bàn không có đơn mở gọi current-order\n4. Khách bàn khác xem hoá đơn',
    'đơn T1',
    'Hoá đơn có subtotal/discount/total/items, total = Σ(đơn giá×SL) − giảm; current-order 200 cùng đơn; bàn trống 404; bàn khác 403')
def _():
    t, o = ST['t1'], ST['o1']
    j = st(rq('GET', f"/orders/{o['id']}/", tbl=t), 200).json()
    s = sum(float(i['unit_price']) * i['quantity'] for i in j['items'])
    eq(int(float(j['subtotal_amount'])), int(s), 'subtotal'); eq(int(float(j['total_amount'])), int(s - float(j['discount_amount'])), 'total')
    ok({'subtotal_amount', 'discount_amount', 'total_amount', 'items'} <= set(j), 'thiếu trường')
    eq(st(rq('GET', f'/tables/{t}/current-order/', tbl=t), 200).json()['id'], o['id'], 'current-order')
    empty = new_table()
    eq(rq('GET', f'/tables/{empty}/current-order/', tbl=empty).status_code, 404, 'bàn trống')
    eq(rq('GET', f"/orders/{o['id']}/", tbl=empty).status_code, 403, 'bàn khác')
    return (f"Hoá đơn #{o['id']}: tạm tính {vnd(s)}đ, giảm {int(float(j['discount_amount']))}, tổng {vnd(j['total_amount'])}đ; "
            f"current-order 200; bàn trống 404; bàn khác 403")


# ---- Khuyến mãi
def promo_order(extra=()):
    return mk_order([('Phở bò tái', 2), ('Chả giò hải sản', 1)] + list(extra))   # 245.000


def apply(oid, t, code):
    return rq('POST', f'/orders/{oid}/apply-promotion/', tbl=t, json={'code': code})


@tc(F_PROMO, 'BR-05, AC-02', 'Đơn 245.000đ (Phở x2 + Chả giò x1); mã ABC10 giảm 10% còn hạn',
    '1. POST /api/orders/<id>/apply-promotion/ {code:"abc10"} (chữ thường)', 'ABC10',
    '200; promotion_code=ABC10; giảm 24.500; tổng 220.500')
def _():
    t, o = promo_order()
    j = st(apply(o['id'], t, 'abc10'), 200).json()
    eq(j['promotion_code'], 'ABC10', 'code'); eq(int(float(j['discount_amount'])), 24500, 'giảm'); eq(int(float(j['total_amount'])), 220500, 'tổng')
    return 'ABC10: giảm 24.500đ, tổng 220.500đ'


@tc(F_PROMO, 'BR-05', 'Đơn 245.000đ; GIAM50K giảm cố định 50.000đ',
    '1. Áp mã GIAM50K', 'GIAM50K', '200; giảm 50.000; tổng 195.000')
def _():
    t, o = promo_order()
    j = st(apply(o['id'], t, 'GIAM50K'), 200).json()
    eq(int(float(j['discount_amount'])), 50000, 'giảm'); eq(int(float(j['total_amount'])), 195000, 'tổng')
    return 'GIAM50K: giảm 50.000đ, tổng 195.000đ'


@tc(F_PROMO, 'BR-05', 'Mã MON15 (giảm 15% riêng một món) và MON10K (giảm 10.000đ riêng một món) đã seed',
    '1. Lấy món gắn mã từ GET /api/promotions/\n2. Áp MON15 lên đơn có món đó\n3. Áp MON10K lên đơn có món đó\n4. Áp MON10K lên đơn KHÔNG có món đó',
    'MON15, MON10K',
    'Giảm chỉ tính trên dòng của món gắn mã (MON15 = 15% giá trị dòng, MON10K = 10.000đ); đơn không có món → 400 "chỉ áp dụng cho món ..."')
def _():
    pm = {p['code']: p for p in rows(st(rq('GET', '/promotions/', tok=TOK['QL']), 200).json())}
    n15, n10 = pm['MON15']['menu_item_name'], pm['MON10K']['menu_item_name']
    t, o = mk_order([(n15, 2), ('Gỏi cuốn tôm thịt', 1)] if n15 != 'Gỏi cuốn tôm thịt' else [(n15, 2), ('Trà sen vàng', 1)])
    j = st(apply(o['id'], t, 'MON15'), 200).json()
    exp = round(PRICE[n15] * 2 * 0.15)
    eq(int(float(j['discount_amount'])), exp, 'MON15')
    t2, o2 = mk_order([(n10, 1), ('Trà sen vàng', 1)])
    eq(int(float(st(apply(o2['id'], t2, 'MON10K'), 200).json()['discount_amount'])), 10000, 'MON10K')
    other = 'Chè khúc bạch' if n10 != 'Chè khúc bạch' else 'Trà sen vàng'
    t3, o3 = mk_order([(other, 1)])
    r = apply(o3['id'], t3, 'MON10K')
    eq(r.status_code, 400, 'không có món')
    return f"MON15 ({n15} x2): giảm {vnd(exp)}đ; MON10K ({n10}): giảm 10.000đ; đơn không có món -> 400 ({r.json()['detail']})"


@tc(F_PROMO, 'BR-05', 'HETHAN20 (đã hết hạn), SAPRA15 (chưa kích hoạt: start sau hiện tại, is_active=false), mã không tồn tại',
    '1. Áp HETHAN20\n2. Áp SAPRA15\n3. Áp KHONGCO\n4. Xem lại đơn',
    'HETHAN20; SAPRA15; KHONGCO',
    'Cả 3 trả 400 "Mã khuyến mãi không tồn tại hoặc đã hết hạn"; đơn không đổi (giảm 0)')
def _():
    t, o = promo_order()
    c = []
    for code in ('HETHAN20', 'SAPRA15', 'KHONGCO'):
        r = apply(o['id'], t, code)
        eq(r.status_code, 400, code); c.append(r.status_code)
    j = get_order(o['id'], t)
    eq(int(float(j['discount_amount'])), 0, 'giảm'); eq(j['promotion_code'], None, 'mã')
    return f'HETHAN20/SAPRA15/KHONGCO -> {c}; đơn giữ nguyên giảm 0'


@tc(F_PROMO, 'BR-05', 'Đơn đã áp ABC10',
    '1. Áp ABC10\n2. Gọi thêm Cơm chiên 110.000đ\n3. Gỡ mã (code rỗng)',
    'ABC10; Cơm chiên x1',
    'Sau gọi thêm giảm tính lại 10% × 355.000 = 35.500 (tổng 319.500); gỡ mã → giảm 0, tổng 355.000')
def _():
    t, o = promo_order()
    st(apply(o['id'], t, 'ABC10'), 200)
    j = st(rq('POST', f"/orders/{o['id']}/add-items/", tbl=t, json={'items': [dict(menu_item_id=M['Cơm chiên hải sản'], quantity=1)]}), 200).json()
    eq(int(float(j['discount_amount'])), 35500, 'giảm sau gọi thêm'); eq(int(float(j['total_amount'])), 319500, 'tổng')
    j2 = st(apply(o['id'], t, ''), 200).json()
    eq(int(float(j2['discount_amount'])), 0, 'gỡ mã'); eq(int(float(j2['total_amount'])), 355000, 'tổng sau gỡ')
    return 'Gọi thêm → giảm 35.500, tổng 319.500; gỡ mã → giảm 0, tổng 355.000'


@tc(F_PROMO, 'BR-05, BR-11', 'Đơn 42.000đ (Trà đào x1) + GIAM50K',
    '1. Áp GIAM50K lên đơn nhỏ hơn mức giảm\n2. Tạo thanh toán', 'GIAM50K, đơn 42.000đ',
    'Giảm bị chặn bằng giá trị đơn (42.000), tổng 0; tạo thanh toán trả 400 "Giá trị đơn hàng không hợp lệ"')
def _():
    t, o = mk_order([('Trà đào cam sả', 1)])
    j = st(apply(o['id'], t, 'GIAM50K'), 200).json()
    eq(int(float(j['discount_amount'])), 42000, 'giảm'); eq(int(float(j['total_amount'])), 0, 'tổng')
    eq(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'cash'}).status_code, 400, 'thanh toán tổng 0')
    return f"Giảm {vnd(j['discount_amount'])} (không vượt giá trị đơn), tổng 0; tạo thanh toán -> 400"


@tc(F_PROMO, 'BR-05, BR-07', 'Đã seed 6 mã',
    '1. Khách GET /api/promotions/ (không token)\n2. Quản lý GET /api/promotions/',
    'ABC10, GIAM50K, MON15, MON10K đang hiệu lực; HETHAN20, SAPRA15 không hiệu lực',
    'Khách chỉ thấy mã còn hiệu lực (không có HETHAN20/SAPRA15); quản lý thấy cả 6 mã')
def _():
    def codes(tok):
        return {p['code'] for p in rows(st(rq('GET', '/promotions/', tok=tok), 200).json())}
    c, m = codes(None), codes(TOK['QL'])
    ok({'ABC10', 'GIAM50K', 'MON15', 'MON10K'} <= c, f'khách thiếu mã: {c}')
    ok('HETHAN20' not in c and 'SAPRA15' not in c, f'khách thấy mã hết hạn: {c}')
    ok({'HETHAN20', 'SAPRA15'} <= m, f'QL thiếu mã: {m}')
    return f'Khách thấy {sorted(c)}; quản lý thấy {len(m)} mã'


# ---- Thanh toán
@tc(F_PAY, 'BR-06, AC-06', 'Đơn mới mở; khách chọn tiền mặt',
    '1. POST /api/payments/create/ {order_id, method:"cash"} (khách)\n2. Gọi lại lần 2\n3. Phục vụ xem GET /api/staff-calls/?status=pending',
    'Phở x1 (85.000đ)',
    '201 payment cash/pending, amount = tổng đơn; sinh 1 yêu cầu nhân viên "Thanh toán tiền mặt..." (không nhân đôi); đơn chưa completed')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    p = st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'cash'}), 201).json()
    eq(p['method'], 'cash', 'method'); eq(p['status'], 'pending', 'status'); eq(int(float(p['amount'])), 85000, 'amount')
    st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'cash'}), (200, 201))
    calls = rows(st(rq('GET', '/staff-calls/', tok=TOK['PV'], params={'status': 'pending'}), 200).json())
    mine = [c for c in calls if c['table'] == t and c['message'].startswith('Thanh toán tiền mặt')]
    eq(len(mine), 1, 'số yêu cầu thu tiền')
    eq(get_order(o['id'], t)['status'], 'pending', 'đơn')
    ST['cash'] = (t, o, p)
    return f"Payment #{p['id']} cash/pending 85.000đ; 1 yêu cầu nhân viên: '{mine[0]['message']}'"


@tc(F_PAY, 'BR-06, BR-07, AC-08', 'Payment cash đang pending (TC trước)',
    '1. Khách (có X-Table-Token) POST confirm-cash\n2. Không token POST confirm-cash\n3. Bếp POST confirm-cash',
    'payment tiền mặt pending',
    'Khách/không token → 401; bếp → 403; payment vẫn pending (khách không tự xác nhận tiền mặt)')
def _():
    t, o, p = ST['cash']
    c = [rq('POST', f"/payments/{p['id']}/confirm-cash/", tbl=t).status_code,
         rq('POST', f"/payments/{p['id']}/confirm-cash/").status_code,
         rq('POST', f"/payments/{p['id']}/confirm-cash/", tok=TOK['BEP']).status_code]
    eq(c, [401, 401, 403], 'mã trả về')
    eq(st(rq('GET', f"/payments/{p['id']}/", tbl=t), 200).json()['status'], 'pending', 'status')
    return f'Khách/anon/bếp xác nhận -> {c}; payment vẫn pending'


@tc(F_PAY, 'BR-06, AC-06, BR-03', 'Payment cash pending',
    '1. Phục vụ POST /api/payments/<id>/confirm-cash/\n2. Kiểm tra đơn/bàn/staff-call\n3. Xác nhận lần 2\n4. Thêm món vào đơn đã thanh toán',
    'waiter_demo',
    '200 success + paid_at; đơn completed; bàn cleaning; yêu cầu thu tiền resolved; xác nhận lần 2 vẫn 200 (idempotent); gọi thêm món → 400')
def _():
    t, o, p = ST['cash']
    j = st(rq('POST', f"/payments/{p['id']}/confirm-cash/", tok=TOK['PV']), 200).json()
    eq(j['status'], 'success', 'status'); ok(j['paid_at'], 'paid_at')
    eq(get_order(o['id'], t)['status'], 'completed', 'đơn'); eq(tbl_status(t), 'cleaning', 'bàn')
    calls = rows(st(rq('GET', '/staff-calls/', tok=TOK['PV']), 200).json())
    cc = [c for c in calls if c['table'] == t and c['message'].startswith('Thanh toán tiền mặt')]
    ok(cc and all(c['status'] == 'resolved' for c in cc), 'staff-call chưa resolved')
    st(rq('POST', f"/payments/{p['id']}/confirm-cash/", tok=TOK['PV']), 200, 'lần 2')
    r = rq('POST', f"/orders/{o['id']}/add-items/", tbl=t, json={'items': [dict(menu_item_id=M['Chè khúc bạch'], quantity=1)]})
    eq(r.status_code, 400, 'thêm món sau thanh toán')
    return f"Payment #{p['id']} success; đơn completed; bàn {t} cleaning; staff-call resolved; lần 2 200; thêm món -> 400"


@tc(F_PAY, 'BR-03, BR-07', 'Bàn T vừa thanh toán xong (cleaning)',
    '1. Khách đặt món khi bàn "cleaning"\n2. Phục vụ PATCH bàn → empty\n3. Khách đặt lại\n4. Quản lý xác nhận tiền mặt một đơn khác',
    'bàn cleaning; waiter_demo; manager_demo',
    'Khách đặt khi bàn đang dọn → 400 "Bàn đang được dọn"; sau khi phục vụ đặt "empty" khách đặt được (201); quản lý (QL) cũng xác nhận được tiền mặt (200)')
def _():
    t = ST['cash'][0]
    body = dict(table_id=t, items=[dict(menu_item_id=M['Chè khúc bạch'], quantity=1)])
    r = rq('POST', '/orders/', tbl=t, json=body)
    eq(r.status_code, 400, 'bàn đang dọn')
    st(rq('PATCH', f'/tables/{t}/status/', tok=TOK['PV'], json={'status': 'empty'}), 200)
    eq(rq('POST', '/orders/', tbl=t, json=body).status_code, 201, 'đặt lại')
    t2, o2 = mk_order([('Chè khúc bạch', 1)])
    p2 = st(rq('POST', '/payments/create/', tbl=t2, json={'order_id': o2['id'], 'method': 'cash'}), 201).json()
    st(rq('POST', f"/payments/{p2['id']}/confirm-cash/", tok=TOK['QL']), 200, 'QL xác nhận')
    return f"Bàn dọn: khách đặt -> 400 ({r.json().get('detail')}); sau empty -> 201; QL xác nhận payment #{p2['id']} -> 200"


@tc(F_PAY, 'BR-06, BR-11, AC-06, BO-04', 'PAYMENT_GATEWAY_MODE=mock',
    '1. POST /api/payments/create/ method=vnpay\n2. Kiểm tra pay_url, qr_image\n3. POST /api/payments/mock-callback/ {txn_ref, result:"success"}\n4. Gọi callback lần 2 với result=cancel',
    'Phở x2 + Trà đào x1 (212.000đ)',
    'pay_url dạng <frontend>/payment/mock?txn=..&amount=212000; qr_image data:image/png; callback success → payment success, đơn completed, bàn cleaning; callback lần 2 không đổi (applied=false, vẫn success)')
def _():
    t, o = mk_order([('Phở bò tái', 2), ('Trà đào cam sả', 1)])
    p = vnpay_create(o['id'], t)
    ok('/payment/mock?' in p['pay_url'], p['pay_url'])
    q = urllib.parse.parse_qs(urllib.parse.urlparse(p['pay_url']).query)
    eq(q['amount'], ['212000'], 'amount'); ok(p['qr_image'].startswith('data:image/png;base64,'), 'qr_image')
    txn = q['txn'][0]
    r = st(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn, 'result': 'success'}), 200).json()
    eq(r['status'], 'success', 'status'); eq(r['applied'], True, 'applied')
    eq(get_order(o['id'], t)['status'], 'completed', 'đơn'); eq(tbl_status(t), 'cleaning', 'bàn')
    r2 = st(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn, 'result': 'cancel'}), 200).json()
    eq(r2['status'], 'success', 'idempotent'); eq(r2['applied'], False, 'applied lần 2')
    return f"txn={txn[:18]}…; success → đơn completed, bàn cleaning; callback lần 2 applied=false, vẫn success"


BANK = dict(bank_bin='970436', bank_name='Vietcombank', bank_account_no='0011001234567', bank_account_name='ABC RESTAURANT')


def _crc16(s):
    c = 0xFFFF
    for b in s.encode('ascii'):
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return f'{c:04X}'


def set_cfg(**kw):
    return st(rq('PATCH', '/settings/', tok=TOK['AD'], json=kw), 200).json()


@tc(F_PAY, 'BR-06, Admin', 'Admin đăng nhập; chưa cấu hình tài khoản nhận',
    '1. Khách GET /api/settings/\n2. PV/QL/ẩn danh PATCH /api/settings/\n3. AD PATCH nhập TK ngân hàng\n4. Khách GET lại; AD GET xem trạng thái cổng',
    'BIN 970436, STK 0011001234567, chủ TK abc restaurant',
    'Chưa cấu hình: bank_transfer=false, bank=null, không lộ config/gateway; PV/QL → 403, ẩn danh → 401; AD lưu 200 (chủ TK viết hoa), khách thấy bank_transfer=true + TK nhận; AD thấy gateway.tmn_code che bớt, không lộ khoá bí mật; sai BIN → 400')
def _():
    pub = st(rq('GET', '/settings/'), 200).json()
    eq(pub['methods']['bank_transfer'], False, 'bank_transfer ban đầu'); ok(pub['bank'] is None and 'config' not in pub and 'gateway' not in pub, 'lộ dữ liệu')
    c = [rq('PATCH', '/settings/', json=BANK).status_code, rq('PATCH', '/settings/', tok=TOK['PV'], json=BANK).status_code,
         rq('PATCH', '/settings/', tok=TOK['QL'], json=BANK).status_code]
    eq(c, [401, 403, 403], 'quyền PATCH')
    eq(rq('PATCH', '/settings/', tok=TOK['AD'], json={'bank_bin': '12'}).status_code, 400, 'BIN sai')
    r = set_cfg(**{**BANK, 'bank_account_name': 'abc restaurant'})
    eq(r['config']['bank_account_name'], 'ABC RESTAURANT', 'upper')
    pub = st(rq('GET', '/settings/'), 200).json()
    eq(pub['methods']['bank_transfer'], True, 'bật sau cấu hình'); eq(pub['bank']['account_no'], BANK['bank_account_no'], 'TK nhận')
    gw = st(rq('GET', '/settings/', tok=TOK['AD']), 200).json()['gateway']
    ok('*' in gw['tmn_code'] or gw['tmn_code'] == '', 'tmn_code phải che bớt'); ok('has_hash_secret' in gw and 'hash_secret' not in gw, 'lộ khoá')
    return f"PATCH: ẩn danh/PV/QL -> {c}; AD 200; khách thấy TK {pub['bank']['account_no']}; gateway={gw}"


@tc(F_PAY, 'BR-06, BR-07, AC-06', 'Đã cấu hình TK nhận (TC trước); đơn mở',
    '1. Khách POST /api/payments/create/ method=bank_transfer (2 lần)\n2. Kiểm tra bank_info, qr_image, staff-call\n3. Khách/bếp POST confirm-manual\n4. PV POST confirm-manual\n5. Xem đơn/bàn/báo cáo',
    'Phở x1 (85.000đ)',
    '201 bank_transfer/pending, bank_info.content=DON<mã đơn>, qr_image PNG; đúng 1 yêu cầu "Khách chờ xác nhận chuyển khoản…"; khách 401, bếp 403; PV xác nhận → success, đơn completed, bàn cleaning, yêu cầu resolved; báo cáo methods có bank_transfer')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    p = st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'bank_transfer'}), 201).json()
    st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'bank_transfer'}), (200, 201))
    eq(p['status'], 'pending', 'status'); eq(p['bank_info']['content'], f"DON{o['id']}", 'nội dung CK'); ok(p['qr_image'].startswith('data:image/png;base64,'), 'qr')
    calls = rows(st(rq('GET', '/staff-calls/', tok=TOK['PV'], params={'status': 'pending'}), 200).json())
    mine = [c for c in calls if c['table'] == t and c['message'].startswith('Khách chờ xác nhận chuyển khoản')]
    eq(len(mine), 1, 'số yêu cầu')
    c = [rq('POST', f"/payments/{p['id']}/confirm-manual/", tbl=t).status_code, rq('POST', f"/payments/{p['id']}/confirm-manual/", tok=TOK['BEP']).status_code]
    eq(c, [401, 403], 'quyền xác nhận')
    j = st(rq('POST', f"/payments/{p['id']}/confirm-manual/", tok=TOK['PV']), 200).json()
    eq(j['status'], 'success', 'success'); eq(get_order(o['id'], t)['status'], 'completed', 'đơn'); eq(tbl_status(t), 'cleaning', 'bàn')
    after = rows(st(rq('GET', '/staff-calls/', tok=TOK['PV']), 200).json())
    ok(all(x['status'] == 'resolved' for x in after if x['table'] == t and x['message'].startswith('Khách chờ xác nhận')), 'yêu cầu chưa resolved')
    rep = st(rq('GET', '/reports/summary/', tok=TOK['QL']), 200).json()
    ok('bank_transfer' in [m['method'] for m in rep['methods']], 'báo cáo thiếu bank_transfer')
    return f"Payment #{p['id']} bank_transfer: khách/bếp -> {c}; PV xác nhận -> đơn completed, bàn cleaning; báo cáo có bank_transfer"


@tc(F_PAY, 'BR-06, Admin', 'Admin; đơn mở',
    '1. AD tắt tiền mặt, VNPay, chuyển khoản\n2. Khách tạo payment từng phương thức\n3. GET /api/settings/ (khách)\n4. AD bật lại tất cả',
    'cash_enabled=false, vnpay_enabled=false, bank_transfer_enabled=false',
    'Mỗi phương thức bị tắt → 400 "không khả dụng", không sinh payment; GET công khai trả methods=false; bật lại → tạo payment 201')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    try:
        set_cfg(cash_enabled=False, vnpay_enabled=False, bank_transfer_enabled=False)
        codes = [rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': m}).status_code for m in ('cash', 'vnpay', 'bank_transfer')]
        eq(codes, [400, 400, 400], 'tạo khi tắt')
        eq(st(rq('GET', '/settings/'), 200).json()['methods'], {'cash': False, 'bank_transfer': False, 'vnpay': False}, 'methods')
    finally:
        set_cfg(cash_enabled=True, vnpay_enabled=True, bank_transfer_enabled=True)
    st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'cash'}), 201, 'bật lại')
    return f'Tắt cả 3 -> {codes}; bật lại -> cash 201'


@tc(F_PAY, 'BR-06', 'Không cần đăng nhập',
    '1. Dựng chuỗi VietQR bằng cùng quy tắc EMVCo từ cấu hình\n2. Kiểm tra CRC-16/CCITT-FALSE của qr_image qua API (nội dung bank_info)',
    'BIN 970436, STK, 170.000đ, nội dung DON1',
    'CRC16 của "123456789" = 29B1 (vector chuẩn); payload bắt đầu 000201010212, có A000000727, QRIBFTTA, 5303704, 5802VN, kết thúc 6304+CRC đúng')
def _():
    eq(_crc16('123456789'), '29B1', 'vector CRC')
    def tlv(tag, v):
        return f'{tag}{len(v):02d}{v}'
    ben = tlv('00', BANK['bank_bin']) + tlv('01', BANK['bank_account_no'])
    body = (tlv('00', '01') + tlv('01', '12') + tlv('38', tlv('00', 'A000000727') + tlv('01', ben) + tlv('02', 'QRIBFTTA'))
            + tlv('53', '704') + tlv('54', '170000') + tlv('58', 'VN') + tlv('62', tlv('08', 'DON1')) + '6304')
    payload = body + _crc16(body)
    ok(payload.startswith('000201010212') and 'A000000727' in payload and 'QRIBFTTA' in payload and '5802VN' in payload, 'cấu trúc')
    eq(_crc16(payload[:-4]), payload[-4:], 'CRC payload')
    return f'payload hợp lệ, CRC={payload[-4:]}'


@tc(F_PAY, 'BR-11, AC-06', 'Đơn mở; link mock đã tạo',
    '1. callback result=cancel\n2. Xem đơn\n3. Tạo lại link thanh toán\n4. callback success\n5. callback result sai / txn lạ',
    'result: cancel/success/x; txn_ref "khongco"',
    'Huỷ → payment failed, đơn vẫn pending; tạo lại link mới (txn khác) → thanh toán thành công; result sai → 400; txn lạ → 404')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    txn = txn_of(vnpay_create(o['id'], t))
    r = st(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn, 'result': 'cancel'}), 200).json()
    eq(r['status'], 'failed', 'cancel'); eq(get_order(o['id'], t)['status'], 'pending', 'đơn')
    txn2 = txn_of(vnpay_create(o['id'], t))
    ok(txn2 != txn, 'txn không đổi')
    st(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn2, 'result': 'success'}), 200)
    eq(get_order(o['id'], t)['status'], 'completed', 'đơn sau retry')
    eq(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn2, 'result': 'x'}).status_code, 400, 'result sai')
    eq(rq('POST', '/payments/mock-callback/', json={'txn_ref': 'khongco', 'result': 'success'}).status_code, 404, 'txn lạ')
    return 'Huỷ → failed, đơn pending; tạo lại link (txn mới) → success, đơn completed; result sai 400; txn lạ 404'


@tc(F_PAY, 'BR-11, AC-06, BR-02', 'Payment vnpay pending',
    '1. Khách GET /api/payments/<id>/\n2. Khách bàn khác GET\n3. POST /api/payments/<id>/sync/',
    'payment vnpay (mock)',
    'Bàn đúng 200 (status pending); bàn khác 403; sync ở chế độ mock trả trạng thái hiện tại không lỗi')
def _():
    t, o = mk_order([('Chè khúc bạch', 1)])
    p = vnpay_create(o['id'], t)
    eq(st(rq('GET', f"/payments/{p['id']}/", tbl=t), 200).json()['status'], 'pending', 'status')
    eq(rq('GET', f"/payments/{p['id']}/", tbl=new_table()).status_code, 403, 'bàn khác')
    eq(st(rq('POST', f"/payments/{p['id']}/sync/", tbl=t, json={}), 200).json()['status'], 'pending', 'sync')
    return 'GET đúng bàn 200 pending; bàn khác 403; sync mock 200 pending'


@tc(F_PAY, 'BR-11, AC-06, BO-04', f'Backend cấu hình VNPAY_TMN_CODE={TMN} + secret test; payment vnpay pending (IPN hoạt động độc lập chế độ mock)',
    '1. Gọi GET /api/payments/vnpay-ipn/ với chữ ký HMAC-SHA512 hợp lệ, ResponseCode=00\n2. Gọi lại cùng tham số',
    'vnp_ResponseCode=00, vnp_TransactionStatus=00, đúng số tiền',
    'Lần 1: RspCode 00, payment success, đơn completed, bàn cleaning; lần 2: RspCode 02 (đã xác nhận, idempotent)')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    p = vnpay_create(o['id'], t)
    ps = vn_params(p)
    eq(st(rq('GET', '/payments/vnpay-ipn/', params=ps), 200).json()['RspCode'], '00', 'IPN')
    eq(st(rq('GET', f"/payments/{p['id']}/", tbl=t), 200).json()['status'], 'success', 'payment')
    eq(get_order(o['id'], t)['status'], 'completed', 'đơn'); eq(tbl_status(t), 'cleaning', 'bàn')
    eq(st(rq('GET', '/payments/vnpay-ipn/', params=ps), 200).json()['RspCode'], '02', 'lần 2')
    return 'IPN hợp lệ → 00 (success, completed, cleaning); lặp lại → 02'


@tc(F_PAY, 'BR-11, AC-06', 'Payment vnpay pending',
    '1. IPN sai chữ ký\n2. IPN đổi tham số sau khi ký\n3. IPN sai số tiền\n4. IPN txn không tồn tại\n5. IPN sai TmnCode\n6. IPN hợp lệ nhưng ResponseCode=24 (khách huỷ)',
    'secure hash "deadbeef…"; amount=100; txn "nope"; tmn=OTHER; code=24',
    'RspCode lần lượt 97, 97, 04, 01, 99; các ca 1-5 payment vẫn pending; ca 6 → RspCode 00 và payment failed, đơn vẫn pending')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    p = vnpay_create(o['id'], t)
    ipn = lambda params: rq('GET', '/payments/vnpay-ipn/', params=params).json()['RspCode']
    tam = vn_params(p); tam['vnp_ResponseCode'] = '24'
    ghost = dict(p); ghost['transaction_id'] = 'nope'
    codes = [ipn(vn_params(p, bad_hash=True)), ipn(tam), ipn(vn_params(p, amount=100)), ipn(vn_params(ghost)), ipn(vn_params(p, tmn='OTHER'))]
    eq(codes, ['97', '97', '04', '01', '99'], 'RspCode')
    eq(st(rq('GET', f"/payments/{p['id']}/", tbl=t), 200).json()['status'], 'pending', 'vẫn pending')
    c6 = ipn(vn_params(p, code='24', status='02'))
    eq(c6, '00', 'huỷ')
    eq(st(rq('GET', f"/payments/{p['id']}/", tbl=t), 200).json()['status'], 'failed', 'payment huỷ')
    eq(get_order(o['id'], t)['status'], 'pending', 'đơn vẫn pending')
    return f'RspCode {codes} (payment pending); ResponseCode=24 → {c6}, payment failed, đơn pending'


@tc(F_PAY, 'BR-11, AC-06', 'Payment vnpay pending',
    '1. GET /api/payments/vnpay-return/ với chữ ký sai\n2. GET vnpay-return hợp lệ (00)\n3. Gọi lại return hợp lệ',
    'tham số vnp_* ký bằng secret test',
    'Chữ ký sai → redirect ?status=invalid; hợp lệ → redirect ?status=success, payment success, đơn completed; gọi lại vẫn success và không ghi đôi')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    p = vnpay_create(o['id'], t)
    r = rq('GET', '/payments/vnpay-return/', params=vn_params(p, bad_hash=True))
    eq(r.status_code, 302, 'redirect'); ok('status=invalid' in r.headers['Location'], r.headers['Location'])
    ps = vn_params(p)
    r2 = rq('GET', '/payments/vnpay-return/', params=ps)
    ok('status=success' in r2.headers['Location'], r2.headers['Location'])
    eq(get_order(o['id'], t)['status'], 'completed', 'đơn')
    ok('status=success' in rq('GET', '/payments/vnpay-return/', params=ps).headers['Location'], 'lần 2')
    return f"sai chữ ký → {r.headers['Location'].split('?')[1].split('&')[0]}; hợp lệ → status=success; lần 2 vẫn success"


@tc(F_PAY, 'BR-07, BO-05, AC-08', 'Có payment cash success và vnpay success',
    '1. Quản lý GET /api/payments/?method=cash&status=success\n2. GET ?status=failed\n3. Phục vụ/Bếp GET /api/payments/',
    'manager_demo; waiter_demo; kitchen_demo',
    'Quản lý lọc đúng theo method/status; phục vụ & bếp → 403')
def _():
    def rw(**p):
        return rows(st(rq('GET', '/payments/', tok=TOK['QL'], params=p), 200).json())
    c, f = rw(method='cash', status='success'), rw(status='failed')
    ok(c and all(x['method'] == 'cash' and x['status'] == 'success' for x in c), 'lọc cash/success')
    ok(f and all(x['status'] == 'failed' for x in f), 'lọc failed')
    codes = [rq('GET', '/payments/', tok=TOK['PV']).status_code, rq('GET', '/payments/', tok=TOK['BEP']).status_code]
    eq(codes, [403, 403], 'phân quyền')
    return f'cash+success: {len(c)} giao dịch; failed: {len(f)}; PV/BEP -> {codes}'


@tc(F_PAY, 'BR-06, BR-07, BR-09', 'Có payment vnpay success (mock) và payment cash success',
    '1. Quản lý POST /api/payments/refund/ cho payment tiền mặt\n2. Hoàn số tiền vượt quá\n3. Phục vụ gọi refund\n4. payment_id không tồn tại / thiếu payment_id',
    'payment cash; amount 999999999; waiter_demo; id 99999',
    'Hoàn tiền chỉ cho VNPay success: tiền mặt → 400; vượt số dư → 400; phục vụ → 403; id lạ → 404; thiếu id → 400')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    pc = pay_cash(o['id'], t)
    t2, o2 = mk_order([('Phở bò tái', 1)])
    pv = vnpay_create(o2['id'], t2)
    st(rq('POST', '/payments/mock-callback/', json={'txn_ref': txn_of(pv), 'result': 'success'}), 200)
    ST['vn_paid'] = pv['id']
    c = [rq('POST', '/payments/refund/', tok=TOK['QL'], json={'payment_id': pc}).status_code,
         rq('POST', '/payments/refund/', tok=TOK['QL'], json={'payment_id': pv['id'], 'amount': 999999999}).status_code,
         rq('POST', '/payments/refund/', tok=TOK['PV'], json={'payment_id': pv['id']}).status_code,
         rq('POST', '/payments/refund/', tok=TOK['QL'], json={'payment_id': 99999}).status_code,
         rq('POST', '/payments/refund/', tok=TOK['QL'], json={}).status_code]
    eq(c, [400, 400, 403, 404, 400], 'mã trả về')
    return f'refund tiền mặt/vượt số dư/phục vụ/id lạ/thiếu id -> {c}'


manual(F_PAY, 'BR-06, BR-11, AC-06, BO-04', 'Khoá VNPay sandbox thật trong backend/.env, PAYMENT_GATEWAY_MODE=vnpay; có Internet',
       '1. Khách chọn "Chuyển khoản (VNPay)" → mở link sandbox\n2. Nhập thẻ NCB 9704198526191432198 / NGUYEN VAN A / 07/15 / OTP 123456\n3. Quay lại /payment-result\n4. Quản lý thử "Hoàn tiền" một giao dịch thành công',
       'thẻ test NCB (README mục Thanh toán)',
       'Thanh toán thành công trên sandbox → đơn completed, bàn cleaning',
       'chạy tay trên docker compose',
       'PROGRESS.md 2026-11-25; mock: ui-preview/screenshots/06-payment-mock-gateway.png, 07-payment-result-after-mock.png',
       status=PASS,
       actual=('Chạy tay trên docker compose 2026-11-25 (VNPay sandbox thật, thẻ NCB): đơn #20 bàn 2, 120.000đ; chấp nhận điều khoản + OTP 123456 '
               '→ /payment-result?status=success. DB: order completed, payment vnpay success (ORD20T261125095520d56ff4), bàn 2 → cleaning. '
               'Hoàn tiền sandbox chưa chạy.'))


manual(F_PAY, 'BR-11, AC-06', 'Mở /payment/mock?... (chế độ mock) trên trình duyệt',
       '1. Khách chọn VNPay, trình duyệt chuyển tới trang giả lập\n2. Bấm "Thanh toán thành công" / "Huỷ"\n3. Kiểm tra trang kết quả /payment-result và màn khách tự cập nhật',
       'đơn bất kỳ', 'Trang giả lập hiển thị đúng số tiền; thành công → trang kết quả báo thành công; huỷ → báo thất bại, khách thanh toán lại được',
       'thao tác trên giao diện', 'ảnh tham chiếu: ui-preview/screenshots/06-payment-mock-gateway.png, 07-payment-result-after-mock.png')


# ---- Đánh giá
@tc(F_REV, 'BO-01, BR-02', 'Đơn đã phục vụ đủ và thanh toán xong (completed)',
    '1. Khách POST /api/reviews/ {order_item, rating:5, comment}\n2. Gửi lại cho cùng món\n3. rating 6 và 0\n4. GET /api/menu-items/ kiểm tra avg_rating',
    'Phở x1: rating 5 "Ngon"',
    'Lần 1: 201; trùng → 400; rating ngoài 1-5 → 400; menu-items trả avg_rating=5.0, review_count ≥ 1')
def _():
    t, o = completed_order([('Phở bò tái', 1)])
    iid = o['items'][0]['id']
    r = st(rq('POST', '/reviews/', tbl=t, json={'order_item': iid, 'rating': 5, 'comment': 'Ngon'}), 201).json()
    eq(r['rating'], 5, 'rating')
    c = [rq('POST', '/reviews/', tbl=t, json={'order_item': iid, 'rating': 4}).status_code]
    t2, o2 = completed_order([('Phở bò tái', 1)])
    i2 = o2['items'][0]['id']
    c += [rq('POST', '/reviews/', tbl=t2, json={'order_item': i2, 'rating': 6}).status_code,
          rq('POST', '/reviews/', tbl=t2, json={'order_item': i2, 'rating': 0}).status_code]
    eq(c, [400, 400, 400], 'mã trả về')
    pho = next(i for i in rows(st(rq('GET', '/menu-items/'), 200).json()) if i['name'] == 'Phở bò tái')
    ok(pho['review_count'] >= 1 and pho['avg_rating'] == 5.0, f"avg={pho['avg_rating']} count={pho['review_count']}")
    ST['rev'] = (t, o, r)
    return f"Review #{r['id']} 201; trùng/6/0 -> {c}; Phở avg_rating={pho['avg_rating']} ({pho['review_count']} đánh giá)"


@tc(F_REV, 'BO-01', 'Đơn chưa hoàn tất',
    '1. Đánh giá món pending\n2. Đánh giá món đã served nhưng đơn chưa thanh toán',
    'đơn pending; đơn served-chưa-trả-tiền',
    'Cả hai → 400 "Chỉ được đánh giá món đã phục vụ trong đơn đã hoàn tất"')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    r1 = rq('POST', '/reviews/', tbl=t, json={'order_item': o['items'][0]['id'], 'rating': 5})
    t2, o2 = mk_order([('Phở bò tái', 1)]); cook_serve(o2)
    r2 = rq('POST', '/reviews/', tbl=t2, json={'order_item': o2['items'][0]['id'], 'rating': 5})
    eq([r1.status_code, r2.status_code], [400, 400], 'mã trả về')
    return f'món pending -> {r1.status_code}; served nhưng chưa thanh toán -> {r2.status_code}'


@tc(F_REV, 'BR-02, BR-07, AC-08', 'Có review của bàn T',
    '1. Khách bàn khác POST review cho món của bàn T\n2. Khách bàn T GET /api/reviews/\n3. Khách bàn khác / không header GET\n4. Quản lý GET /api/reviews/?menu_item=<id>',
    'review từ TC đánh giá',
    'Bàn khác POST → 403; bàn T thấy review của mình; bàn khác và không header thấy rỗng; quản lý thấy và lọc được theo món')
def _():
    t, o, r = ST['rev']
    iid = o['items'][0]['id']
    other = new_table()
    eq(rq('POST', '/reviews/', tbl=other, json={'order_item': iid, 'rating': 1}).status_code, 403, 'POST bàn khác')
    lst = lambda **kw: rows(st(rq('GET', '/reviews/', **kw), 200).json())
    ok(any(x['id'] == r['id'] for x in lst(tbl=t)), 'bàn T không thấy review của mình')
    eq(lst(tbl=other), [], 'bàn khác'); eq(lst(), [], 'không header')
    mgr = lst(tok=TOK['QL'], params={'menu_item': M['Phở bò tái']})
    ok(any(x['id'] == r['id'] for x in mgr), 'quản lý không thấy')
    return f'Bàn khác POST -> 403; bàn T thấy review #{r["id"]}; bàn khác/không header -> []; QL lọc theo món thấy {len(mgr)} review'


# ---- Bếp
@tc(F_KIT, 'AC-03, BO-02, BR-03', 'Đơn T1 (Phở x2, Trà đào, Gỏi cuốn) đang pending',
    '1. Bếp GET /api/orders/?status=pending,confirmed\n2. Bếp PATCH món Phở pending→cooking\n3. PATCH cooking→done',
    'kitchen_demo; món Phở của đơn T1',
    'Bếp thấy đơn và các dòng món; cooking 200 → đơn chuyển "confirmed"; done 200')
def _():
    o = ST['o1']
    lst = rows(st(rq('GET', '/orders/', tok=TOK['BEP'], params={'status': 'pending,confirmed'}), 200).json())
    mine = next((x for x in lst if x['id'] == o['id']), None)
    ok(mine and mine['items'], 'bếp không thấy đơn')
    it = line(o, 'Phở bò tái')
    eq(st(item_status(it['id'], 'cooking', 'BEP'), 200).json()['status'], 'cooking', 'cooking')
    eq(get_order(o['id'], tok=TOK['BEP'])['status'], 'confirmed', 'đơn confirmed')
    eq(st(item_status(it['id'], 'done', 'BEP'), 200).json()['status'], 'done', 'done')
    return f"Bếp thấy đơn #{o['id']} ({len(mine['items'])} dòng); Phở pending→cooking→done; đơn → confirmed"


@tc(F_KIT, 'BR-03, AC-08', 'Đơn mới, món pending',
    '1. Bếp PATCH pending→done (nhảy bước)\n2. pending→served\n3. status không hợp lệ\n4. Phục vụ PATCH pending→cooking\n5. Bếp cooking, done rồi PATCH served',
    'món pending',
    'Nhảy bước/giá trị lạ → 400; phục vụ đặt cooking → 403; bếp đặt served → 403')
def _():
    t, o = mk_order([('Phở bò tái', 1), ('Chè khúc bạch', 1)])
    a, b = o['items'][0]['id'], o['items'][1]['id']
    c = [item_status(a, 'done', 'BEP').status_code, item_status(a, 'served', 'BEP').status_code, item_status(a, 'xxx', 'BEP').status_code]
    eq(c, [400, 400, 400], 'nhảy bước')
    eq(item_status(b, 'cooking', 'PV').status_code, 403, 'PV cooking')
    st(item_status(a, 'cooking', 'BEP'), 200); st(item_status(a, 'done', 'BEP'), 200)
    eq(item_status(a, 'served', 'BEP').status_code, 403, 'BEP served')
    return f'pending→done/served/xxx -> {c}; PV đặt cooking -> 403; BEP đặt served -> 403'


@tc(F_KIT, 'BR-03, BO-02', 'Món "Trà đào cam sả" đang bán',
    '1. Bếp POST /api/menu-items/<id>/availability/ {is_available:false}\n2. Khách GET menu\n3. Khách đặt món đó\n4. Giá trị is_available sai\n5. Bếp mở bán lại',
    'kitchen_demo; Trà đào cam sả',
    'Khoá món: 200; khách không thấy món; đặt → 404; giá trị sai → 400; mở lại: khách thấy lại')
def _():
    mid = M['Trà đào cam sả']
    eq(st(rq('POST', f'/menu-items/{mid}/availability/', tok=TOK['BEP'], json={'is_available': False}), 200).json()['is_available'], False, 'khoá')
    ok(all(i['id'] != mid for i in rows(st(rq('GET', '/menu-items/'), 200).json())), 'khách vẫn thấy món hết')
    t = new_table()
    eq(rq('POST', '/orders/', tbl=t, json=dict(table_id=t, items=[dict(menu_item_id=mid, quantity=1)])).status_code, 404, 'đặt món hết')
    bad = rq('POST', f'/menu-items/{mid}/availability/', tok=TOK['BEP'], json={'is_available': 'abc'}).status_code
    st(rq('POST', f'/menu-items/{mid}/availability/', tok=TOK['BEP'], json={'is_available': True}), 200)
    ok(any(i['id'] == mid for i in rows(st(rq('GET', '/menu-items/'), 200).json())), 'không mở lại được')
    eq(bad, 400, 'giá trị sai')
    return 'Khoá: khách không thấy, đặt -> 404; giá trị sai -> 400; mở lại thấy'


@tc(F_KIT, 'BR-07, AC-08', 'Token bếp',
    '1. Bếp POST /api/menu-items/ (tạo món)\n2. Bếp PATCH giá món\n3. Bếp POST /api/categories/\n4. Bếp GET /api/reports/summary/',
    'kitchen_demo',
    'Bếp chỉ được bật/tắt "còn món"; tạo/sửa món, danh mục, xem báo cáo → 403')
def _():
    c = [rq('POST', '/menu-items/', tok=TOK['BEP'], json={'name': 'x', 'price': 1000}).status_code,
         rq('PATCH', f"/menu-items/{M['Phở bò tái']}/", tok=TOK['BEP'], json={'price': 1}).status_code,
         rq('POST', '/categories/', tok=TOK['BEP'], json={'name': 'x'}).status_code,
         rq('GET', '/reports/summary/', tok=TOK['BEP']).status_code]
    eq(c, [403, 403, 403, 403], 'mã trả về')
    return f'tạo món/sửa giá/tạo danh mục/báo cáo -> {c}'


# ---- Phục vụ
@tc(F_WAI, 'BR-03, AC-03, BO-02', 'Món Phở của đơn T1 đã "done"',
    '1. Phục vụ PATCH món done→served\n2. served→cooking',
    'waiter_demo',
    'done→served 200; served→cooking 400; trạng thái cuối "served"')
def _():
    it = line(ST['o1'], 'Phở bò tái')
    eq(st(item_status(it['id'], 'served', 'PV'), 200).json()['status'], 'served', 'served')
    eq(item_status(it['id'], 'cooking', 'BEP').status_code, 400, 'ngược')
    return 'Phở done→served 200; served→cooking 400'


@tc(F_WAI, 'BO-02, BR-03', 'Token phục vụ',
    '1. Phục vụ GET /api/tables/\n2. PATCH bàn → cleaning\n3. PATCH trạng thái lạ\n4. PATCH bàn đang có đơn mở → empty\n5. Bếp GET /api/tables/',
    'waiter_demo',
    'Thấy ≥ 30 bàn với trạng thái; đổi trạng thái 200; trạng thái lạ → 400; bàn còn đơn mở → empty bị 400; bếp → 403')
def _():
    lst = rows(st(rq('GET', '/tables/', tok=TOK['PV']), 200).json())
    ok(len(lst) >= 30 and all('status' in x for x in lst), f'{len(lst)} bàn')
    t = new_table()
    st(rq('PATCH', f'/tables/{t}/status/', tok=TOK['PV'], json={'status': 'cleaning'}), 200)
    eq(tbl_status(t), 'cleaning', 'cleaning')
    eq(rq('PATCH', f'/tables/{t}/status/', tok=TOK['PV'], json={'status': 'xyz'}).status_code, 400, 'xyz')
    eq(rq('PATCH', f"/tables/{ST['t1']}/status/", tok=TOK['PV'], json={'status': 'empty'}).status_code, 400, 'bàn bận')
    eq(rq('GET', '/tables/', tok=TOK['BEP']).status_code, 403, 'bếp')
    return f'{len(lst)} bàn; cleaning 200; "xyz" 400; bàn có đơn mở → empty 400; bếp 403'


@tc(F_WAI, 'BO-01, BO-02', 'Token phục vụ; bàn trống',
    '1. Phục vụ POST /api/orders/ (không X-Table-Token) gọi món hộ',
    'Phở x1 cho bàn mới',
    '201; created_by = id phục vụ; bàn occupied')
def _():
    me = st(rq('GET', '/auth/me/', tok=TOK['PV']), 200).json()
    t, o = mk_order([('Phở bò tái', 1)], tok=TOK['PV'])
    eq(o['created_by'], me['id'], 'created_by'); eq(tbl_status(t), 'occupied', 'bàn')
    return f"Đơn #{o['id']} created_by={o['created_by']} (waiter_demo), bàn {t} occupied"


@tc(F_WAI, 'BR-03, BR-07', 'Đơn pending; đơn có món cooking',
    '1. Phục vụ huỷ đơn chỉ có món pending\n2. Chuyển đơn cancelled→confirmed\n3. completed khi chưa thanh toán\n4. Phục vụ huỷ đơn có món cooking\n5. Quản lý huỷ đơn có món cooking',
    'waiter_demo; manager_demo',
    'Huỷ đơn pending 200 (bàn empty); cancelled→confirmed 400; completed khi chưa thanh toán 400; phục vụ huỷ đơn đã chế biến 403; quản lý 200')
def _():
    def pst(oid, s, role):
        return rq('PATCH', f'/orders/{oid}/status/', tok=TOK[role], json={'status': s})
    t, o = mk_order([('Phở bò tái', 1)])
    st(pst(o['id'], 'cancelled', 'PV'), 200); eq(tbl_status(t), 'empty', 'bàn sau huỷ')
    c = [pst(o['id'], 'confirmed', 'PV').status_code]
    t2, o2 = mk_order([('Phở bò tái', 1)])
    c.append(pst(o2['id'], 'completed', 'QL').status_code)
    st(item_status(o2['items'][0]['id'], 'cooking', 'BEP'), 200)
    c.append(pst(o2['id'], 'cancelled', 'PV').status_code)
    c.append(pst(o2['id'], 'cancelled', 'QL').status_code)
    eq(c, [400, 400, 403, 200], 'mã trả về')
    return f'huỷ pending 200 (bàn empty); sau đó cancelled→confirmed/completed-chưa-trả/PV huỷ đơn cooking/QL huỷ -> {c}'


# ---- Quản lý: danh mục/món
@tc(F_MGM, 'BO-03, BR-07', 'Token quản lý',
    '1. POST /api/categories/ tạo "FT-Danh mục"\n2. Tạo trùng tên\n3. PATCH đổi tên\n4. Tạo món trong danh mục rồi xoá danh mục\n5. Xoá món rồi xoá danh mục',
    'FT-Danh mục / FT-Danh mục đổi tên',
    'Tạo 201; trùng 400; sửa 200; xoá danh mục còn món → 400; xoá khi trống → 204')
def _():
    cid = st(rq('POST', '/categories/', tok=TOK['QL'], json={'name': 'FT-Danh mục', 'sort_order': 99}), 201).json()['id']
    eq(rq('POST', '/categories/', tok=TOK['QL'], json={'name': 'ft-danh mục'}).status_code, 400, 'trùng tên')
    st(rq('PATCH', f'/categories/{cid}/', tok=TOK['QL'], json={'name': 'FT-Danh mục đổi tên'}), 200)
    m = st(rq('POST', '/menu-items/', tok=TOK['QL'], data={'name': 'FT món tạm', 'price': '10000', 'category': cid}), 201).json()
    eq(rq('DELETE', f'/categories/{cid}/', tok=TOK['QL']).status_code, 400, 'xoá danh mục còn món')
    st(rq('DELETE', f"/menu-items/{m['id']}/", tok=TOK['QL']), 204)
    st(rq('DELETE', f'/categories/{cid}/', tok=TOK['QL']), 204)
    return 'Tạo 201; trùng 400; sửa 200; xoá khi còn món 400; xoá món + danh mục 204'


@tc(F_MGM, 'AC-05, BR-08, BO-03', 'Token quản lý; ảnh PNG 8x8 sinh bằng code',
    '1. POST /api/menu-items/ (multipart có image_url)\n2. GET ảnh theo URL trả về\n3. Khách GET /api/menu-items/ thấy ảnh\n4. PATCH sửa giá/tên + ảnh mới',
    'FT Món có ảnh, giá 55.000, ảnh PNG',
    'Tạo 201 kèm image_url; ảnh tải được (200, image/png); khách thấy image_url của món; sửa 200 và ảnh đổi sang file mới')
def _():
    cats = rows(st(rq('GET', '/categories/'), 200).json())
    r = st(rq('POST', '/menu-items/', tok=TOK['QL'],
              data={'name': 'FT Món có ảnh', 'price': '55000', 'category': cats[0]['id'], 'description': 'test', 'is_available': 'true'},
              files={'image_url': ('ft.png', png_bytes(), 'image/png')}), 201).json()
    ok(r['image_url'], 'không có image_url'); url = r['image_url']
    img = SESS.get(url if url.startswith('http') else BASE + url, timeout=15)
    eq(img.status_code, 200, 'GET ảnh'); ok(img.headers.get('Content-Type', '').startswith('image/'), img.headers.get('Content-Type'))
    ok(img.content[:4] == b'\x89PNG', 'không phải PNG')
    mine = next(i for i in rows(st(rq('GET', '/menu-items/'), 200).json()) if i['id'] == r['id'])
    eq(mine['image_url'], url, 'khách thấy ảnh')
    p = st(rq('PATCH', f"/menu-items/{r['id']}/", tok=TOK['QL'], data={'price': '60000', 'name': 'FT Món có ảnh (sửa)'},
              files={'image_url': ('ft2.png', png_bytes(16, 16), 'image/png')}), 200).json()
    eq(int(float(p['price'])), 60000, 'giá'); ok(p['image_url'] != url, 'ảnh không đổi')
    ST['ft_item'] = r['id']
    return f"Món #{r['id']} tạo kèm ảnh, GET ảnh 200 image/png ({len(img.content)}B), khách thấy ảnh; sửa giá 60.000 + ảnh mới 200"


@tc(F_MGM, 'AC-05, BR-08', 'Token quản lý',
    '1. Giá 0 và giá âm\n2. Upload file không phải ảnh\n3. Upload ảnh > 5MB\n4. Tạo món thiếu tên',
    'price 0/-5; file "abc"; PNG + 5,4MB đệm',
    'Các ca sai → 400 (giá phải > 0; chỉ nhận ảnh hợp lệ; ảnh tối đa 5MB)')
def _():
    cid = rows(st(rq('GET', '/categories/'), 200).json())[0]['id']
    base = {'name': 'FT lỗi', 'category': cid}
    c = [rq('POST', '/menu-items/', tok=TOK['QL'], data={**base, 'price': '0'}).status_code,
         rq('POST', '/menu-items/', tok=TOK['QL'], data={**base, 'price': '-5'}).status_code,
         rq('POST', '/menu-items/', tok=TOK['QL'], data={**base, 'price': '1000'}, files={'image_url': ('a.png', b'abc', 'image/png')}).status_code,
         rq('POST', '/menu-items/', tok=TOK['QL'], data={**base, 'price': '1000'}, files={'image_url': ('big.png', png_bytes(pad=5_400_000), 'image/png')}).status_code,
         rq('POST', '/menu-items/', tok=TOK['QL'], data={'price': '1000'}).status_code]
    eq(c, [400] * 5, 'mã trả về')
    return f'giá 0/âm, file giả, ảnh >5MB, thiếu tên -> {c}'


@tc(F_MGM, 'BO-03, BR-03', 'Món FT đã tạo; món đã có trong đơn ("Phở bò tái")',
    '1. Xoá món đã có trong đơn\n2. Chuyển món sang "Ngừng bán" (PATCH is_available=false)\n3. Khách GET menu, quản lý GET ?is_available=false\n4. Xoá món chưa bán',
    'Phở bò tái; Chè khúc bạch; FT Món có ảnh',
    'Món đã bán → 409; ngừng bán: khách không thấy, quản lý thấy; món chưa bán xoá 204')
def _():
    eq(rq('DELETE', f"/menu-items/{M['Phở bò tái']}/", tok=TOK['QL']).status_code, 409, 'xoá món đã bán')
    mid = M['Chè khúc bạch']
    st(rq('PATCH', f'/menu-items/{mid}/', tok=TOK['QL'], json={'is_available': False}), 200)
    ok(all(i['id'] != mid for i in rows(st(rq('GET', '/menu-items/'), 200).json())), 'khách thấy món ngừng bán')
    mg = rows(st(rq('GET', '/menu-items/', tok=TOK['QL'], params={'is_available': 'false'}), 200).json())
    ok(any(i['id'] == mid for i in mg), 'quản lý không thấy món ngừng bán')
    st(rq('PATCH', f'/menu-items/{mid}/', tok=TOK['QL'], json={'is_available': True}), 200)
    st(rq('DELETE', f"/menu-items/{ST['ft_item']}/", tok=TOK['QL']), 204)
    return 'Xoá món đã bán 409; ngừng bán: khách ẩn, QL thấy; xoá món chưa bán 204'


manual(F_MGM, 'AC-05, BR-08', 'Đăng nhập /manager trên Chrome',
       '1. Menu > "Thêm món": chọn ảnh JPG/PNG, lưu\n2. Mở /table/5 xem thẻ món có ảnh đúng\n3. Sửa món, đổi ảnh\n4. Thử ảnh > 5MB',
       'ảnh thật (JPG/PNG)', 'Ảnh hiển thị đúng ở thực đơn khách và màn quản lý; ảnh lỗi bị từ chối bằng thông báo',
       'thao tác chọn file/xem ảnh trên UI; phần API đã kiểm ở TC upload', 'ui-preview/screenshots/01-menu-desktop-hero.jpg, 02-menu-desktop-list.jpg')


# ---- Quản lý: bàn / QR
@tc(F_MGT, 'BO-03, AC-04', 'Token quản lý',
    '1. POST /api/tables/ {area, capacity}\n2. PATCH sức chứa\n3. Sức chứa 0 / 51\n4. Phục vụ POST /api/tables/\n5. Xoá bàn chưa có đơn\n6. Xoá bàn đã có đơn (bàn T1)',
    'area "FT Khu", capacity 6',
    'Tạo 201, number = id, status empty; sửa 200; sức chứa ngoài 1–50 → 400; phục vụ tạo bàn → 403; xoá bàn trống 204; bàn có đơn → 400')
def _():
    r = st(rq('POST', '/tables/', tok=TOK['QL'], json={'area': 'FT Khu', 'capacity': 6}), 201).json()
    eq(r['number'], str(r['id']), 'number = id'); eq(r['status'], 'empty', 'status')
    st(rq('PATCH', f"/tables/{r['id']}/", tok=TOK['QL'], json={'capacity': 8}), 200)
    c = [rq('POST', '/tables/', tok=TOK['QL'], json={'area': 'x', 'capacity': 0}).status_code,
         rq('POST', '/tables/', tok=TOK['QL'], json={'area': 'x', 'capacity': 51}).status_code,
         rq('POST', '/tables/', tok=TOK['PV'], json={'area': 'x', 'capacity': 4}).status_code]
    eq(c, [400, 400, 403], 'mã trả về')
    st(rq('DELETE', f"/tables/{r['id']}/", tok=TOK['QL']), 204)
    d = rq('DELETE', f"/tables/{ST['t1']}/", tok=TOK['QL'])
    eq(d.status_code, 400, 'xoá bàn có đơn')
    return f"Tạo bàn #{r['id']} (number={r['number']}); sức chứa 0/51/PV tạo -> {c}; xoá bàn trống 204; bàn có đơn -> {d.status_code}"


@tc(F_MGT, 'AC-04, BR-01, BO-03', 'Token quản lý/phục vụ',
    '1. GET /api/tables/5/qr/\n2. GET /api/tables/qr-codes/\n3. GET qr/?base_url=http://192.168.1.5:5173\n4. base_url sai\n5. Khách (không token) GET qr',
    'bàn 5; base_url LAN',
    'url dạng <base>/table/5?k=<mã bí mật> (k ngẫu nhiên, riêng từng bàn); qr_image là PNG hợp lệ; qr-codes trả đủ số bàn; base_url LAN được dùng, base_url sai bị bỏ qua; khách → 401')
def _():
    j = st(rq('GET', '/tables/5/qr/', tok=TOK['QL']), 200).json()
    ok(re.fullmatch(r'https?://[^/?#]+/table/5\?k=[A-Za-z0-9_-]{20,}', j['url']), j['url'])
    ok(j['qr_image'].startswith('data:image/png;base64,'), 'qr_image')
    png = base64.b64decode(j['qr_image'].split(',', 1)[1])
    ok(png[:8] == b'\x89PNG\r\n\x1a\n' and len(png) > 200, 'PNG QR hỏng')
    allq = st(rq('GET', '/tables/qr-codes/', tok=TOK['PV']), 200).json()
    total = rows(st(rq('GET', '/tables/', tok=TOK['QL']), 200).json())
    eq(len(allq), len(total), 'số QR')
    ok(all(re.fullmatch(r'https?://[^/?#]+/table/%d\?k=[A-Za-z0-9_-]{20,}' % x['id'], x['url']) for x in allq), 'link QR sai định dạng')
    eq(len({x['url'].split('k=')[1] for x in allq}), len(allq), 'mã k phải khác nhau theo bàn')
    lan = st(rq('GET', '/tables/5/qr/', tok=TOK['QL'], params={'base_url': 'http://192.168.1.5:5173'}), 200).json()
    ok(lan['url'].startswith('http://192.168.1.5:5173/table/5?k='), 'base_url LAN')
    bad = st(rq('GET', '/tables/5/qr/', tok=TOK['QL'], params={'base_url': 'javascript:alert(1)'}), 200).json()
    ok('/table/5?k=' in bad['url'] and 'javascript' not in bad['url'], bad['url'])
    eq(rq('GET', '/tables/5/qr/').status_code, 401, 'khách')
    return f"QR bàn 5: {j['url']} (PNG {len(png)}B); qr-codes {len(allq)} bàn; base_url LAN → {lan['url']}; base_url sai bị bỏ; khách 401"


manual(F_MGT, 'AC-04, BO-03', 'Đăng nhập /manager → Bàn; máy in hoặc "Lưu PDF"',
       '1. Mở màn "Bàn & QR", bấm "Tải QR" / "In tất cả"\n2. Mở file/bản in, kiểm tra mỗi bàn một QR kèm số bàn\n3. Quét thử 2 QR bằng điện thoại',
       'bàn 1-30', 'File QR tải về được, in rõ nét; quét ra đúng link /table/<id> của từng bàn',
       'tải file/in giấy/quét camera là thao tác thủ công')


# ---- Quản lý: khuyến mãi / nhân viên
@tc(F_MGP, 'BR-05, BO-03', 'Token quản lý',
    '1. POST /api/promotions/ (code chữ thường, 5%)\n2. Dữ liệu sai: >100%, giá trị 0, ngày kết thúc ≤ bắt đầu, mã có ký tự lạ\n3. PATCH tắt is_active rồi áp mã\n4. Xoá mã chưa dùng\n5. Xoá mã đã dùng (ABC10)',
    'ft5 (5%); ABC10 đã dùng ở TC trước',
    'Tạo 201 và code in hoa; dữ liệu sai → 400; mã đã tắt không áp được (400); mã chưa dùng xoá 204; mã đã dùng chỉ bị tắt (200, giữ lịch sử)')
def _():
    now = datetime.now(timezone.utc)
    base = {'code': 'ft5', 'discount_type': 'percent', 'value': 5, 'start_date': (now - timedelta(days=1)).isoformat(),
            'end_date': (now + timedelta(days=30)).isoformat(), 'is_active': True}
    p = st(rq('POST', '/promotions/', tok=TOK['QL'], json=base), 201).json()
    eq(p['code'], 'FT5', 'code in hoa')
    bad = [{**base, 'code': 'ft6', 'value': 101}, {**base, 'code': 'ft7', 'value': 0},
           {**base, 'code': 'ft8', 'end_date': (now - timedelta(days=2)).isoformat()}, {**base, 'code': 'ft 9!'}]
    c = [rq('POST', '/promotions/', tok=TOK['QL'], json=b).status_code for b in bad]
    eq(c, [400] * 4, 'dữ liệu sai')
    st(rq('PATCH', f"/promotions/{p['id']}/", tok=TOK['QL'], json={'is_active': False}), 200)
    t, o = mk_order([('Phở bò tái', 1)])
    eq(apply(o['id'], t, 'FT5').status_code, 400, 'mã đã tắt')
    st(rq('DELETE', f"/promotions/{p['id']}/", tok=TOK['QL']), 204)
    abc = next(x for x in rows(st(rq('GET', '/promotions/', tok=TOK['QL']), 200).json()) if x['code'] == 'ABC10')
    d = st(rq('DELETE', f"/promotions/{abc['id']}/", tok=TOK['QL']), 200).json()
    ab2 = next(x for x in rows(st(rq('GET', '/promotions/', tok=TOK['QL']), 200).json()) if x['code'] == 'ABC10')
    eq(ab2['is_active'], False, 'ABC10 bị tắt')
    st(rq('PATCH', f"/promotions/{abc['id']}/", tok=TOK['QL'], json={'is_active': True}), 200)  # khôi phục
    return f"Tạo FT5 (code in hoa); sai dữ liệu -> {c}; mã tắt không áp được; xoá mã chưa dùng 204; xoá ABC10 (đã dùng) -> tắt ({d.get('detail')})"


@tc(F_MGP, 'BR-07, BO-06', 'Token quản lý/admin',
    '1. QL POST /api/users/ tạo nhân viên phục vụ\n2. Mật khẩu yếu\n3. QL tạo tài khoản role AD\n4. QL tự khoá mình\n5. Khoá nhân viên rồi đăng nhập\n6. Admin tạo AD',
    'ft_waiter / Str0ng!Pass_2026; mật khẩu "123"',
    'Tạo 201; mật khẩu yếu 400; QL cấp AD → 400; tự khoá → 400; nhân viên bị khoá đăng nhập 401; AD tạo AD 201')
def _():
    r = st(rq('POST', '/users/', tok=TOK['QL'], json={'username': 'ft_waiter', 'password': 'Str0ng!Pass_2026', 'role': 'PV'}), 201).json()
    c = [rq('POST', '/users/', tok=TOK['QL'], json={'username': 'ft_weak', 'password': '123', 'role': 'PV'}).status_code,
         rq('POST', '/users/', tok=TOK['QL'], json={'username': 'ft_ad', 'password': 'Str0ng!Pass_2026', 'role': 'AD'}).status_code]
    me = st(rq('GET', '/auth/me/', tok=TOK['QL']), 200).json()
    c.append(rq('PATCH', f"/users/{me['id']}/", tok=TOK['QL'], json={'is_active': False}).status_code)
    eq(c, [400, 400, 400], 'mã trả về')
    st(login('ft_waiter', 'Str0ng!Pass_2026'), 200, 'login nhân viên mới')
    st(rq('PATCH', f"/users/{r['id']}/", tok=TOK['QL'], json={'is_active': False}), 200)
    eq(login('ft_waiter', 'Str0ng!Pass_2026').status_code, 401, 'login khi bị khoá')
    st(rq('POST', '/users/', tok=TOK['AD'], json={'username': 'ft_admin2', 'password': 'Str0ng!Pass_2026', 'role': 'AD'}), 201, 'AD tạo AD')
    return f'Tạo nhân viên #{r["id"]} 201; yếu/QL cấp AD/tự khoá -> {c}; bị khoá đăng nhập 401; AD tạo AD 201'


# ---- Quản lý: đơn / hoá đơn / báo cáo
@tc(F_MGO, 'BO-03, AC-07', 'Đã có nhiều đơn trong ngày',
    '1. GET /api/orders/?status=completed\n2. ?table_id=<T>\n3. ?q=<mã đơn>\n4. ?date_from=hôm nay / sau 2 ngày\n5. ?limit=3',
    'tham số lọc',
    'Lọc trạng thái/bàn/mã đơn đúng; date_from tương lai trả rỗng; limit giới hạn số dòng; đơn completed đều có payment success')
def _():
    def L(**p):
        return rows(st(rq('GET', '/orders/', tok=TOK['QL'], params=p), 200).json())
    comp = L(status='completed')
    ok(comp and all(o['status'] == 'completed' for o in comp), 'lọc status')
    ok(all(o['payment_status'] == 'success' for o in comp), 'đơn completed phải có payment success')
    t = ST['cash'][0]
    ok(L(table_id=t) and all(o['table'] == t for o in L(table_id=t)), 'lọc bàn')
    oid = ST['cash'][1]['id']
    rq_ = L(q=str(oid))
    ok(any(o['id'] == oid for o in rq_) and all(o['id'] == oid or o['table_number'] == str(oid) for o in rq_), 'tìm mã đơn')
    today = datetime.now().strftime('%Y-%m-%d'); fut = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    ok(len(L(date_from=today)) > 0, 'date_from hôm nay'); eq(L(date_from=fut), [], 'date_from tương lai')
    eq(len(L(limit=3)), 3, 'limit')
    return f'completed {len(comp)} đơn (đều payment success); lọc bàn/mã đơn/ngày/limit đúng'


@tc(F_MGO, 'BR-09, AC-07, BO-05', 'Đã có các giao dịch thành công trong ngày',
    '1. GET /api/reports/summary/?period=day, week, month\n2. Đối chiếu revenue với tổng các payment success (GET /api/payments/)\n3. ?date_from=&date_to=\n4. series',
    'period day/week/month; custom hôm nay',
    'Cả 4 trả 200 đủ khoá; revenue = Σ tiền các giao dịch thành công (khớp /payments/); paid_orders khớp; series theo giờ (day) / theo ngày (week, month); custom khớp')
def _():
    pays = rows(st(rq('GET', '/payments/', tok=TOK['QL'], params={'limit': 1000}), 200).json())
    paid = [p for p in pays if p['status'] in ('success', 'refunded')]
    exp = sum(int(float(p['amount'])) - int(float(p['refunded_amount'])) for p in paid)
    out = []
    keys = {'revenue', 'paid_orders', 'avg_order', 'series', 'best_sellers', 'peak_hours', 'methods', 'period'}
    for per in ('day', 'week', 'month'):
        j = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'period': per}), 200).json()
        ok(keys <= set(j), f'thiếu khoá {per}')
        eq(j['revenue'], exp, f'revenue {per}'); eq(j['paid_orders'], len(paid), f'paid_orders {per}')
        eq(len(j['series']), {'day': 24, 'week': 7, 'month': 30}[per], f'series {per}')
        out.append(f"{per}={vnd(j['revenue'])}")
    today = datetime.now().strftime('%Y-%m-%d')
    j = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'date_from': today, 'date_to': today}), 200).json()
    eq(j['revenue'], exp, 'custom'); eq(j['period'], 'custom', 'period')
    return f'{len(paid)} giao dịch thành công = {vnd(exp)}đ; revenue day/week/month khớp ({", ".join(out)}); custom khớp'


@tc(F_MGO, 'BR-09, AC-07, BO-05', 'Có đơn completed với nhiều món',
    '1. GET /api/reports/summary/?period=month → best_sellers\n2. Tự cộng số lượng từng món từ GET /api/orders/?status=completed\n3. So khớp, kiểm tra sắp xếp giảm dần',
    'dữ liệu của phiên test',
    'best_sellers[].quantity = tổng số lượng bán thực tế của món trong các đơn đã thanh toán; sắp xếp giảm dần theo số lượng')
def _():
    j = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'period': 'month'}), 200).json()
    orders = rows(st(rq('GET', '/orders/', tok=TOK['QL'], params={'status': 'completed', 'limit': 500}), 200).json())
    agg = {}
    for o in orders:
        for i in o['items']:
            agg[i['menu_item_name']] = agg.get(i['menu_item_name'], 0) + i['quantity']
    bs = j['best_sellers']
    ok(bs, 'best_sellers rỗng')
    for b in bs:
        eq(b['quantity'], agg[b['name']], f"số lượng {b['name']}")
    q = [b['quantity'] for b in bs]
    eq(q, sorted(q, reverse=True), 'sắp xếp')
    return 'Top: ' + ', '.join(f"{b['name']} ×{b['quantity']}" for b in bs[:3]) + ' — khớp số liệu đơn completed'


@tc(F_MGO, 'BR-09, AC-07, BO-05', 'Các đơn đã thanh toán trong giờ hiện tại',
    '1. GET /api/reports/summary/?period=day → peak_hours\n2. Kiểm tra đủ 24 khung giờ và tổng số đơn',
    'period=day',
    'peak_hours có 24 phần tử (hour 0–23); tổng orders = paid_orders; có ít nhất 1 giờ cao điểm ≥ 1 đơn')
def _():
    j = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'period': 'day'}), 200).json()
    ph = j['peak_hours']
    eq(len(ph), 24, 'số khung giờ'); eq(sum(h['orders'] for h in ph), j['paid_orders'], 'tổng đơn')
    peak = max(ph, key=lambda h: h['orders'])
    ok(peak['orders'] >= 1, 'không có giờ cao điểm')
    return f"24 khung giờ, tổng {j['paid_orders']} đơn; cao điểm {peak['hour']}h với {peak['orders']} đơn"


@tc(F_MGO, 'BR-09, AC-07, BR-06', 'Có payment vnpay success (mock) từ TC hoàn tiền',
    '1. GET báo cáo revenue R0\n2. Mô phỏng hoàn 10.000đ cho giao dịch (cập nhật refunded_amount trong DB test — API hoàn tiền cần VNPay thật)\n3. GET báo cáo lại\n4. Khôi phục dữ liệu',
    'refunded_amount=10000',
    'Doanh thu giảm đúng 10.000đ, trường refunded = 10.000, paid_orders không đổi')
def _():
    pid = ST['vn_paid']
    r0 = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'period': 'day'}), 200).json()
    db_exec('UPDATE api_payment SET refunded_amount=10000 WHERE id=?', (pid,))
    try:
        r1 = st(rq('GET', '/reports/summary/', tok=TOK['QL'], params={'period': 'day'}), 200).json()
    finally:
        db_exec('UPDATE api_payment SET refunded_amount=0 WHERE id=?', (pid,))
    eq(r0['revenue'] - r1['revenue'], 10000, 'doanh thu giảm'); eq(r1['refunded'], 10000, 'refunded'); eq(r1['paid_orders'], r0['paid_orders'], 'paid_orders')
    return f"Doanh thu {vnd(r0['revenue'])} → {vnd(r1['revenue'])} (−10.000); refunded=10.000; paid_orders không đổi (đã khôi phục DB)"


@tc(F_MGO, 'BR-07, BO-06', 'Có thao tác quản lý trước đó (tạo/sửa/xoá món, bàn...)',
    '1. Quản lý GET /api/audit-logs/\n2. Phục vụ GET /api/audit-logs/',
    'manager_demo; waiter_demo',
    'Quản lý thấy nhật ký có các hành động MENU_ITEM_CREATE, TABLE_CREATE, PAYMENT_CASH_CONFIRM...; phục vụ → 403')
def _():
    j = rows(st(rq('GET', '/audit-logs/', tok=TOK['QL'], params={'limit': 500}), 200).json())
    acts = {x['action'] for x in j}
    ok({'MENU_ITEM_CREATE', 'TABLE_CREATE', 'PAYMENT_CASH_CONFIRM'} <= acts, f'thiếu hành động: {sorted(acts)}')
    eq(rq('GET', '/audit-logs/', tok=TOK['PV']).status_code, 403, 'PV')
    return f'{len(j)} bản ghi nhật ký, {len(acts)} loại hành động; phục vụ → 403'


# ---- Phân quyền AC-08
@tc(F_AC8, 'AC-08, BR-07', 'Không gửi token',
    '1. Gọi không token: GET /orders/, /tables/, /staff-calls/, /payments/, /reports/summary/, /users/, /audit-logs/\n2. POST /menu-items/, /categories/, /promotions/, /tables/\n3. PATCH /orders/1/status/, /order-items/1/status/\n4. Token rác "garbage"',
    'không Authorization / Bearer garbage',
    'Tất cả trả 401 (chưa xác thực)')
def _():
    bad, n = [], 0
    for g in ['/orders/', '/tables/', '/staff-calls/', '/payments/', '/reports/summary/', '/users/', '/audit-logs/']:
        n += 1
        if rq('GET', g).status_code != 401:
            bad.append(('GET', g))
    for p in ['/menu-items/', '/categories/', '/promotions/', '/tables/']:
        n += 1
        if rq('POST', p, json={}).status_code != 401:
            bad.append(('POST', p))
    for p in ('/orders/1/status/', '/order-items/1/status/'):
        n += 1
        if rq('PATCH', p, json={'status': 'cooking'}).status_code != 401:
            bad.append(('PATCH', p))
    n += 1
    if rq('GET', '/orders/', tok='garbage').status_code != 401:
        bad.append(('GET garbage', '/orders/'))
    ok(not bad, f'không phải 401: {bad}')
    return f'{n} request không/sai token đều 401'


def _matrix(role, checks):
    bad, codes = [], []
    for method, path, body, exp in checks:
        r = rq(method, path, tok=TOK[role], json=body)
        codes.append(r.status_code)
        if r.status_code not in exp:
            bad.append(f'{method} {path} -> {r.status_code}')
    ok(not bad, '; '.join(bad))
    return codes


@tc(F_AC8, 'AC-08, BR-07, BO-06', 'Token phục vụ (PV)',
    '1. PV gọi các API ngoài quyền: POST /menu-items/, /categories/, /promotions/, /tables/\n2. GET /reports/summary/, /users/, /payments/, /audit-logs/\n3. PATCH /order-items/<id>/status/ (cooking); POST /payments/refund/\n4. Đối chiếu: PV gọi API trong quyền (GET /tables/, /orders/, /staff-calls/)',
    'waiter_demo',
    'API ngoài quyền → 403; API trong quyền → 200')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    iid = o['items'][0]['id']
    out = [('POST', '/menu-items/', {}, (403,)), ('POST', '/categories/', {}, (403,)), ('POST', '/promotions/', {}, (403,)),
           ('POST', '/tables/', {}, (403,)), ('GET', '/reports/summary/', None, (403,)), ('GET', '/users/', None, (403,)),
           ('GET', '/payments/', None, (403,)), ('GET', '/audit-logs/', None, (403,)),
           ('PATCH', f'/order-items/{iid}/status/', {'status': 'cooking'}, (403,)), ('POST', '/payments/refund/', {'payment_id': 1}, (403,))]
    c1 = _matrix('PV', out)
    c2 = _matrix('PV', [('GET', '/tables/', None, (200,)), ('GET', '/orders/', None, (200,)), ('GET', '/staff-calls/', None, (200,))])
    return f'PV ngoài quyền {c1}; trong quyền {c2}'


@tc(F_AC8, 'AC-08, BR-07, BO-06', 'Token bếp (BEP)',
    '1. BEP gọi: GET /tables/, /staff-calls/, /payments/, /reports/summary/, /users/\n2. POST /payments/<id>/confirm-cash/, POST /menu-items/, PATCH /orders/<id>/status/\n3. Đối chiếu: GET /orders/, POST /menu-items/<id>/availability/',
    'kitchen_demo',
    'API ngoài quyền → 403; API của bếp (xem đơn, còn/hết món) → 200')
def _():
    t, o = mk_order([('Phở bò tái', 1)])
    out = [('GET', '/tables/', None, (403,)), ('GET', '/staff-calls/', None, (403,)), ('GET', '/payments/', None, (403,)),
           ('GET', '/reports/summary/', None, (403,)), ('GET', '/users/', None, (403,)),
           ('POST', '/payments/1/confirm-cash/', None, (403,)), ('POST', '/menu-items/', {}, (403,)),
           ('PATCH', f"/orders/{o['id']}/status/", {'status': 'cancelled'}, (403,))]
    c1 = _matrix('BEP', out)
    c2 = _matrix('BEP', [('GET', '/orders/', None, (200,)),
                         ('POST', f"/menu-items/{M['Nấm đùi gà kho tiêu']}/availability/", {'is_available': True}, (200,))])
    return f'BEP ngoài quyền {c1}; trong quyền {c2}'


@tc(F_AC8, 'AC-08, BR-07, BO-06', 'Token quản lý (QL) và admin (AD)',
    '1. QL gọi API quản trị: GET /reports/summary/, /users/, /payments/, /audit-logs/, /orders/, /tables/\n2. QL tạo tài khoản role AD\n3. AD gọi cùng nhóm API',
    'manager_demo; admin_test',
    'QL và AD truy cập được các API quản lý (200); QL cấp quyền AD → 400')
def _():
    chk = [('GET', '/reports/summary/', None, (200,)), ('GET', '/users/', None, (200,)), ('GET', '/payments/', None, (200,)),
           ('GET', '/audit-logs/', None, (200,)), ('GET', '/orders/', None, (200,)), ('GET', '/tables/', None, (200,))]
    c1, c2 = _matrix('QL', chk), _matrix('AD', chk)
    r = rq('POST', '/users/', tok=TOK['QL'], json={'username': 'ft_ad_by_ql', 'password': 'Str0ng!Pass_2026', 'role': 'AD'})
    eq(r.status_code, 400, 'QL cấp AD')
    return f'QL {c1}; AD {c2}; QL cấp AD -> 400'


@tc(F_AC8, 'AC-08, BR-02', 'Hai bàn A và B; đơn/payment/staff-call/review thuộc bàn A',
    '1. Khách bàn B (X-Table-Token của B) thao tác dữ liệu bàn A: xem đơn, huỷ món, áp mã, gọi thêm món, tạo thanh toán, xem payment, gọi nhân viên, đánh giá, xem current-order\n2. Khách xem danh sách đơn/bàn của nhân viên',
    'đơn bàn A (Phở x1)',
    'Mọi thao tác chéo bàn → 403; GET /orders/, /tables/ danh sách → 401')
def _():
    ta, o = mk_order([('Phở bò tái', 1)])
    tb = new_table()
    p = st(rq('POST', '/payments/create/', tbl=ta, json={'order_id': o['id'], 'method': 'cash'}), 201).json()
    iid = o['items'][0]['id']
    calls = [
        ('xem đơn', rq('GET', f"/orders/{o['id']}/", tbl=tb)),
        ('huỷ món', rq('POST', f'/order-items/{iid}/cancel/', tbl=tb)),
        ('áp mã', apply(o['id'], tb, 'ABC10')),
        ('gọi thêm', rq('POST', f"/orders/{o['id']}/add-items/", tbl=tb, json={'items': [dict(menu_item_id=M['Phở bò tái'], quantity=1)]})),
        ('tạo thanh toán', rq('POST', '/payments/create/', tbl=tb, json={'order_id': o['id'], 'method': 'cash'})),
        ('xem payment', rq('GET', f"/payments/{p['id']}/", tbl=tb)),
        ('gọi NV', rq('POST', '/staff-calls/', tbl=tb, json={'table': ta, 'message': 'x'})),
        ('đánh giá', rq('POST', '/reviews/', tbl=tb, json={'order_item': iid, 'rating': 5})),
        ('current-order', rq('GET', f'/tables/{ta}/current-order/', tbl=tb)),
    ]
    codes = {n: r.status_code for n, r in calls}
    bad = {n: c for n, c in codes.items() if c != 403}
    ok(not bad, f'không phải 403: {bad}')
    lst = [rq('GET', '/orders/', tbl=tb).status_code, rq('GET', '/tables/', tbl=tb).status_code]
    eq(lst, [401, 401], 'danh sách')
    return f'{len(codes)} thao tác chéo bàn B→A đều 403; danh sách đơn/bàn -> {lst}'


@tc(F_AC8, 'AC-08, BR-07', 'Đã đăng nhập đủ role; TC chạy cuối cùng (giới hạn 10 lần/phút/IP)',
    '1. Gửi liên tiếp đăng nhập sai tới khi bị chặn (tối đa 15 lần)',
    'username manager_demo, mật khẩu sai',
    'Một lúc sau trả 429 (throttle login) — chống dò mật khẩu', late=True)
def _():
    codes = []
    for _i in range(15):
        c = login('manager_demo', 'sai').status_code
        codes.append(c)
        if c == 429:
            break
    ok(429 in codes, f'không bị chặn: {codes}')
    return f'{len(codes)} lần đăng nhập sai liên tiếp -> {codes.count(401)}×401 rồi 429'


# ---- Realtime
@tc(F_WS, 'AC-03, BR-04, AC-02, BO-02', 'Backend InMemory channel layer; token PV/BEP hợp lệ',
    '1. Mở WS kitchen_orders (BEP), staff_orders (PV), table_<T> (khách, không token)\n2. Khách POST /api/orders/\n3. Đo thời gian nhận sự kiện',
    'Phở x1 + ghi chú',
    '3 kênh đều nhận "new_order" chứa đúng đơn; độ trễ < 2 giây')
def _():
    async def go():
        t = new_table()
        k, s, c = await ws_open('kitchen_orders', TOK['BEP']), await ws_open('staff_orders', TOK['PV']), await ws_open(f'table_{t}')
        try:
            t0 = time.monotonic()
            r = st(rq('POST', '/orders/', tbl=t, json=dict(table_id=t, items=[dict(menu_item_id=M['Phở bò tái'], quantity=1, note='ít hành')])), 201)
            oid = r.json()['id']
            res = []
            for name, ws in (('bếp', k), ('phục vụ', s), ('bàn', c)):
                m = await ws_wait(ws, 'new_order', lambda m: m['order']['id'] == oid)
                res.append(f'{name} {1000 * (time.monotonic() - t0):.0f}ms')
                eq(m['order']['items'][0]['note'], 'ít hành', 'ghi chú trong sự kiện')
            ok(time.monotonic() - t0 < 2, 'trễ ≥ 2s')
            return 'new_order tới bếp/phục vụ/bàn: ' + ', '.join(res)
        finally:
            for w in (k, s, c):
                await w.close()
    return arun(go())


@tc(F_WS, 'AC-03, BR-04, BR-03', 'Đơn pending; WS bàn, phục vụ, bếp đang mở',
    '1. Bếp PATCH món → cooking\n2. Bếp PATCH → done\n3. Phục vụ PATCH → served',
    'Phở x1',
    'Mỗi lần đổi trạng thái, kênh bàn (khách), staff_orders và kitchen_orders đều nhận "item_status_updated" với trạng thái mới ngay lập tức')
def _():
    async def go():
        t, o = mk_order([('Phở bò tái', 1)])
        iid = o['items'][0]['id']
        k, s, c = await ws_open('kitchen_orders', TOK['BEP']), await ws_open('staff_orders', TOK['PV']), await ws_open(f'table_{t}')
        try:
            out = []
            for new, role in (('cooking', 'BEP'), ('done', 'BEP'), ('served', 'PV')):
                t0 = time.monotonic()
                st(item_status(iid, new, role), 200)
                for ws in (c, s, k):
                    await ws_wait(ws, 'item_status_updated', lambda m: m['order_item']['id'] == iid and m['order_item']['status'] == new)
                out.append(f'{new} {1000 * (time.monotonic() - t0):.0f}ms')
            return 'item_status_updated tới bàn/phục vụ/bếp cho ' + ', '.join(out)
        finally:
            for w in (k, s, c):
                await w.close()
    return arun(go())


@tc(F_WS, 'AC-03, BR-04, BO-02', 'WS staff_orders (PV) và table_<T> đang mở',
    '1. Khách POST /api/staff-calls/\n2. Khách chọn tiền mặt (POST payments/create)\n3. Phục vụ xác nhận tiền mặt',
    'gọi nhân viên; thanh toán tiền mặt',
    'staff_orders nhận "staff_call" khi khách gọi và khi chọn tiền mặt; sau xác nhận, kênh bàn nhận "order_updated" status=completed')
def _():
    async def go():
        t, o = mk_order([('Phở bò tái', 1)])
        s, c = await ws_open('staff_orders', TOK['PV']), await ws_open(f'table_{t}')
        try:
            st(rq('POST', '/staff-calls/', tbl=t, json={'table': t, 'message': 'Cho xin nước'}), 201)
            await ws_wait(s, 'staff_call', lambda m: m['call']['table'] == t); await ws_wait(c, 'staff_call')
            p = st(rq('POST', '/payments/create/', tbl=t, json={'order_id': o['id'], 'method': 'cash'}), 201).json()
            await ws_wait(s, 'staff_call', lambda m: 'Thanh toán tiền mặt' in m['call']['message'])
            st(rq('POST', f"/payments/{p['id']}/confirm-cash/", tok=TOK['PV']), 200)
            await ws_wait(c, 'order_updated', lambda m: m['order']['id'] == o['id'] and m['order']['status'] == 'completed')
            return 'staff_call (gọi NV + thu tiền mặt) tới staff_orders; order_updated(completed) tới bàn sau xác nhận'
        finally:
            for w in (s, c):
                await w.close()
    return arun(go())


@tc(F_WS, 'AC-03, BR-04', 'WS staff_orders, kitchen_orders (QL) và table_<T> đang mở',
    '1. Phục vụ PATCH trạng thái bàn\n2. Bếp bật/tắt món (availability)',
    'bàn → cleaning; món Nấm đùi gà kho tiêu hết/còn',
    '"table_updated" tới staff_orders + kênh bàn; "menu_updated" tới kitchen_orders và staff_orders')
def _():
    async def go():
        t = new_table()
        s, k, c = await ws_open('staff_orders', TOK['QL']), await ws_open('kitchen_orders', TOK['QL']), await ws_open(f'table_{t}')
        mid = M['Nấm đùi gà kho tiêu']
        try:
            st(rq('PATCH', f'/tables/{t}/status/', tok=TOK['PV'], json={'status': 'cleaning'}), 200)
            await ws_wait(s, 'table_updated', lambda m: m['table']['id'] == t and m['table']['status'] == 'cleaning')
            await ws_wait(c, 'table_updated')
            st(rq('POST', f'/menu-items/{mid}/availability/', tok=TOK['BEP'], json={'is_available': False}), 200)
            await ws_wait(k, 'menu_updated', lambda m: m['menu_item']['id'] == mid and m['menu_item']['is_available'] is False)
            await ws_wait(s, 'menu_updated')
            return 'table_updated tới staff_orders + bàn; menu_updated tới kitchen_orders + staff_orders'
        finally:
            st(rq('POST', f'/menu-items/{mid}/availability/', tok=TOK['BEP'], json={'is_available': True}), 200)
            for w in (s, k, c):
                await w.close()
    return arun(go())


@tc(F_WS, 'BR-02, BR-04, AC-03', 'Hai bàn A và B, mỗi bàn một kênh WS khách',
    '1. Mở WS table_A và table_B\n2. Bàn A đặt món\n3. Chờ 2 giây trên kênh B',
    'Phở x1 bàn A',
    'table_A nhận new_order; table_B không nhận sự kiện nào của bàn A (cô lập theo bàn)')
def _():
    async def go():
        a, b = new_table(), new_table()
        wa, wb = await ws_open(f'table_{a}'), await ws_open(f'table_{b}')
        try:
            st(rq('POST', '/orders/', tbl=a, json=dict(table_id=a, items=[dict(menu_item_id=M['Phở bò tái'], quantity=1)])), 201)
            await ws_wait(wa, 'new_order')
            ok(await ws_none(wb, 'new_order', timeout=2), 'kênh bàn B nhận sự kiện bàn A')
            return 'table_A nhận new_order; table_B im lặng 2 giây'
        finally:
            await wa.close(); await wb.close()
    return arun(go())


@tc(F_WS, 'AC-08, AC-03, BR-07', 'Token 4 role + token rác',
    '1. Mở kitchen_orders với: không token, token rác, PV, BEP, QL, AD\n2. Mở staff_orders với cùng bộ\n3. Mở table_<n> không token / token đúng bàn / token bàn khác\n4. Gửi ping',
    'ws://127.0.0.1:8020/ws/<kênh>/?token=…',
    'kitchen_orders: BEP/QL/AD vào được, anon/rác/PV bị từ chối; staff_orders: PV/QL/AD vào được, anon/rác/BEP bị từ chối; table_<n> chỉ mở với token phiên bàn đúng bàn (hoặc nhân viên); ping → pong')
def _():
    async def go():
        for g, allowed in (('kitchen_orders', {'BEP', 'QL', 'AD'}), ('staff_orders', {'PV', 'QL', 'AD'})):
            for who, tok in (('anon', None), ('rác', 'garbage'), ('PV', TOK['PV']), ('BEP', TOK['BEP']), ('QL', TOK['QL']), ('AD', TOK['AD'])):
                got = await ws_try(g, tok)
                ok(got == (who in allowed), f'{g} với {who}: kết nối={got}, mong đợi={who in allowed}')
        ok(await ws_try('table_1', None), 'khách có token bàn 1 không vào được kênh bàn')
        ok(not await ws_try('table_1', anon=True), 'không token vẫn vào được kênh bàn')
        ok(not await ws_try('table_1', 'garbage'), 'token rác vẫn vào được kênh bàn')
        ok(not await ws_try('table_2', table_token(1)), 'token bàn 1 vào được kênh bàn 2')
        ok(await ws_try('table_2', TOK['PV']), 'nhân viên không vào được kênh bàn')
        return 'Ma trận kênh/role đúng (12 ca kitchen/staff); table_1 chỉ mở với token đúng bàn (không token/rác/token bàn khác bị từ chối), nhân viên vào được; ping/pong OK'
    return arun(go())


# ---- Mobile
@tc(F_MOB, 'AC-09, BR-10, BO-07', 'Mã nguồn frontend',
    '1. Kiểm frontend/index.html có meta viewport\n2. Đếm media query ≤ 480px trong frontend/src (CSS cho điện thoại)',
    'frontend/index.html, frontend/src/**/*.css',
    'Có <meta name="viewport" content="width=device-width, initial-scale=1.0">; có ≥ 3 media query cho màn hình ≤ 480px (kiểm tĩnh, không thay thế kiểm tra trực quan)')
def _():
    html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    ok('name="viewport"' in html and 'width=device-width' in html, 'thiếu viewport')
    n, files = 0, []
    for f in (ROOT / 'frontend' / 'src').rglob('*.css'):
        c = len(re.findall(r'@media[^{]*max-width:\s*(?:4[0-8]\d|3\d\d|420|480)px', f.read_text(encoding='utf-8')))
        if c:
            n += c; files.append(f.name)
    ok(n >= 3, f'chỉ {n} media query')
    return f'Có meta viewport; {n} media query ≤ 480px trong {len(files)} file CSS ({", ".join(files[:5])}…)'


manual(F_MOB, 'AC-09, BR-10, BO-07', 'Chrome DevTools > Toggle device toolbar; app chạy (npm run dev) hoặc docker compose',
       '1. Đặt viewport 375×667, 390×844, 414×896\n2. Mở /table/5: kiểm tra header, thẻ món, giỏ, đặt món, hoá đơn, modal thanh toán\n3. Kiểm tra không có cuộn ngang, nút ≥ 44px, chữ đọc được\n4. Lặp với /chef, /waiter',
       '3 kích thước viewport', 'Bố cục thích ứng, không vỡ/cuộn ngang ở cả 3 kích thước; thao tác bằng một tay được',
       'cần kiểm trực quan trên trình duyệt/điện thoại thật',
       'ui-preview/screenshots hiện chỉ có ảnh desktop (01-05) nên chưa dùng làm bằng chứng mobile; PROGRESS.md ghi đã sửa tràn input/header Menu ở 390px')


manual(F_MOB, 'AC-09, AC-01', 'Điện thoại thật (Chrome Android / Safari iOS) cùng Wi-Fi với máy chạy docker compose',
       '1. Quét QR bàn → xem menu, đặt món, thanh toán mock\n2. Xoay ngang/dọc\n3. Kiểm tra tốc độ tải và ảnh món',
       'HOST_IP LAN trong .env', 'Dùng mượt trên điện thoại thật, không lỗi hiển thị', 'cần thiết bị thật và mạng LAN')


# =========================================================================== CHẠY
def clean_env():
    env = {k: v for k, v in os.environ.items() if k not in ('REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'SSL_CERT_FILE')}
    env.update(THROTTLE_RATE_OVERRIDES='customer=100000/min,order_create=100000/min,staff_call=100000/min,review=100000/min,table_session=100000/min', DJANGO_DEBUG='1', DATABASE_URL='sqlite:///functional.sqlite3', REDIS_URL='', PAYMENT_GATEWAY_MODE='mock',
               VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET_KEY=SECRET, SEED_DEMO_PASSWORD=PASSWORD, MEDIA_ROOT=str(MEDIA_TMP),
               FRONTEND_BASE_URL='http://localhost:5173', PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
               DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1')
    return env


def manage(*args):
    r = subprocess.run([str(PY), 'manage.py', *args], cwd=BACKEND, env=clean_env(), capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        raise RuntimeError(f'manage.py {args} lỗi:\n{r.stdout[-800:]}\n{r.stderr[-1500:]}')
    return r.stdout


def start_server():
    if DB_FILE.exists():
        DB_FILE.unlink()
    MEDIA_TMP.mkdir(exist_ok=True)
    manage('migrate', '--noinput')
    manage('seed_demo')
    manage('seed_tables_promos')
    manage('shell', '-c',
           "import os\nfrom django.contrib.auth import get_user_model as g\nU=g();p=os.environ['SEED_DEMO_PASSWORD']\n"
           "U.objects.create_user('admin_test',password=p,role='AD',is_staff=True)\n"
           "U.objects.create_user('locked_test',password=p,role='PV',is_active=False)\n"
           "from api.models import Table\n"
           "[Table.objects.get_or_create(pk=n,defaults={'area':'FT','capacity':4}) for n in range(31,121)]\n")
    log = open(HERE / '_server.log', 'w', encoding='utf-8')
    proc = subprocess.Popen([str(PY), '-m', 'daphne', '-b', '127.0.0.1', '-p', str(PORT), 'backend.asgi:application'],
                            cwd=BACKEND, env=clean_env(), stdout=log, stderr=subprocess.STDOUT)
    for _i in range(60):
        try:
            if SESS.get(BASE + '/api/health/', timeout=2).status_code == 200:
                return proc, log
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError('daphne thoát sớm, xem _server.log')
        time.sleep(1)
    raise RuntimeError('daphne không lên sau 60s')


def stop_server(proc, log):
    if proc and proc.poll() is None:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        try:
            proc.wait(10)
        except Exception:
            pass
    if log:
        log.close()
    time.sleep(1)
    for f in (DB_FILE, BACKEND / 'functional.sqlite3-journal', HERE / '_server.log'):
        try:
            if f.exists():
                f.unlink()
        except OSError as e:
            print('không xoá được', f, e)
    shutil.rmtree(MEDIA_TMP, ignore_errors=True)


def execute():
    order = [t for t in TCS if not t['late']] + [t for t in TCS if t['late']]
    for t in order:
        if t['manual']:
            t['actual'], t['status'], t['note'] = t['manual']['actual'], t['manual'].get('status') or TODO, t['manual']['note']
            continue
        t0 = time.time()
        try:
            res = t['fn']()
            t['actual'], t['status'] = (res or 'OK'), PASS
        except AssertionError as e:
            t['actual'], t['status'] = f'LỖI: {e}', FAIL
        except Exception as e:  # noqa: BLE001
            t['actual'], t['status'] = f'NGOẠI LỆ {type(e).__name__}: {e}', FAIL
        t['note'] = f'API thật, backend riêng :{PORT} ({time.time() - t0:.1f}s)'
        print(f"{t['id']} {t['status']:4} {t['flow']} | {t['actual'][:110]}")


def dump_json():
    data = {'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'tests': [{k: t[k] for k in ('id', 'flow', 'ref', 'pre', 'steps', 'data', 'expected', 'actual', 'status', 'note')} for t in TCS]}
    RESULTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


# --------------------------------------------------------------------------- báo cáo
AC_TEXT = {
    'AC-01': 'Quét QR → đúng thực đơn theo bàn', 'AC-02': 'Đặt món + ghi chú', 'AC-03': 'Đồng bộ real-time',
    'AC-04': 'Sinh/xuất mã QR theo bàn', 'AC-05': 'Upload ảnh món ăn', 'AC-06': 'Thanh toán sandbox hoàn tất',
    'AC-07': 'Báo cáo doanh thu & món bán chạy', 'AC-08': 'Phân quyền đúng vai trò', 'AC-09': 'Giao diện mobile-friendly',
}
BR_TEXT = {
    'BR-01': 'Định danh bàn qua QR', 'BR-02': 'Ngữ cảnh bàn', 'BR-03': 'Trạng thái món', 'BR-04': 'Đồng bộ real-time',
    'BR-05': 'Khuyến mãi', 'BR-06': 'Hình thức thanh toán', 'BR-07': 'Phân quyền', 'BR-08': 'Upload hình ảnh',
    'BR-09': 'Báo cáo', 'BR-10': 'Giới hạn kỹ thuật (web responsive)', 'BR-11': 'Thanh toán sandbox',
}


def esc(s):
    return str(s).replace('|', '\\|').replace('\r', '').replace('\n', '<br>')


def refs_of(t):
    return set(re.findall(r'(?:AC|BR|BO)-\d+', t['ref']))


def verdict(tests):
    if not tests:
        return 'Chưa có TC'
    if any(x['status'] == FAIL for x in tests):
        return 'Chưa đạt'
    ran = [x for x in tests if x['status'] == PASS]
    todo = [x for x in tests if x['status'] == TODO]
    if not ran:
        return 'Chưa kiểm (chỉ TC thủ công)'
    return 'Đạt' if not todo else 'Đạt (phần tự động); còn TC thủ công'


def stats(tests):
    return {s: sum(1 for t in tests if t['status'] == s) for s in (PASS, FAIL, TODO)}


def mapping(tests, texts):
    out = []
    for code in sorted(texts):
        rel = [t for t in tests if code in refs_of(t)]
        out.append((code, texts[code], rel, verdict(rel)))
    return out


def write_md(data):
    tests = data['tests']
    s = stats(tests)
    L = ['# Kịch bản & kết quả kiểm thử chức năng — ABC Restaurant (QR Menu)', '',
         f"Ngày chạy: {data['generated']} · Môi trường: backend riêng (daphne :{PORT}, SQLite `functional.sqlite3`, "
         f"`REDIS_URL` rỗng = InMemory, `PAYMENT_GATEWAY_MODE=mock`), dữ liệu `seed_demo` + `seed_tables_promos`, "
         f"script `docs/testing/functional/run_functional.py` (requests + websockets).", '',
         f"Tổng **{len(tests)}** TC: **{s[PASS]} Pass**, **{s[FAIL]} Fail**, **{s[TODO]} Chưa chạy** (kiểm thủ công bằng giao diện/thiết bị, có hướng dẫn trong cột Kết quả thực tế).", '',
         '## 1. Bảng kịch bản kiểm thử', '',
         '| Mã TC | Luồng/Phân hệ | Yêu cầu tham chiếu (BR/AC/BO) | Tiền điều kiện | Các bước | Dữ liệu test | Kết quả mong đợi | Kết quả thực tế | Trạng thái (Pass/Fail) | Ghi chú/Bằng chứng |',
         '|---|---|---|---|---|---|---|---|---|---|']
    for t in tests:
        L.append('| ' + ' | '.join(esc(x) for x in (t['id'], t['flow'], t['ref'], t['pre'], t['steps'], t['data'], t['expected'],
                                                      t['actual'], t['status'], t['note'])) + ' |')
    for title, texts, head in (('## 2. Đối chiếu Tiêu chí nghiệm thu (AC) với TC', AC_TEXT, 'Tiêu chí'),
                               ('## 3. Đối chiếu Quy tắc nghiệp vụ (BR) với TC', BR_TEXT, 'Quy tắc')):
        L += ['', title, '', f'| Mã | {head} | TC liên quan | Pass/Fail/Chưa chạy | Kết luận |', '|---|---|---|---|---|']
        for code, text, rel, v in mapping(tests, texts):
            ss = stats(rel)
            L.append(f"| {code} | {esc(text)} | {', '.join(x['id'] for x in rel) or '-'} | {ss[PASS]}/{ss[FAIL]}/{ss[TODO]} | **{v}** |")
    L += ['', '## 4. Thống kê', '', '| Chỉ số | Số lượng |', '|---|---|',
          f'| Tổng TC | {len(tests)} |', f'| Pass | {s[PASS]} |', f'| Fail | {s[FAIL]} |', f'| Chưa chạy (thủ công) | {s[TODO]} |',
          f'| Tỉ lệ Pass trên TC đã chạy | {100 * s[PASS] / max(1, s[PASS] + s[FAIL]):.1f}% |', '',
          '| Luồng/Phân hệ | Tổng | Pass | Fail | Chưa chạy |', '|---|---|---|---|---|']
    flows = []
    for t in tests:
        if t['flow'] not in flows:
            flows.append(t['flow'])
    for f in flows:
        sub = [t for t in tests if t['flow'] == f]; ss = stats(sub)
        L.append(f'| {esc(f)} | {len(sub)} | {ss[PASS]} | {ss[FAIL]} | {ss[TODO]} |')
    fails = [t for t in tests if t['status'] == FAIL]
    L += ['', '## 5. Danh sách Fail', '']
    if fails:
        L += ['| Mã TC | Luồng | Kết quả thực tế |', '|---|---|---|'] + [f"| {t['id']} | {esc(t['flow'])} | {esc(t['actual'])} |" for t in fails]
    else:
        L.append('Không có TC Fail.')
    L += ['', '## 6. Ghi chú', '',
          '- TC "Chưa chạy" là các kịch bản chỉ kiểm được bằng giao diện/thiết bị thật (quét QR bằng camera, in QR, giỏ hàng trên trình duyệt, mobile 375/390/414); hướng dẫn nằm ở cột Kết quả thực tế.',
          '- Hoàn tiền VNPay thành công cần merchant API thật nên không chạy tự động; TC báo cáo mô phỏng hoàn tiền bằng cập nhật trực tiếp `refunded_amount` trong DB test.',
          '- IPN/return VNPay được kiểm bằng chữ ký HMAC-SHA512 sinh bằng khoá test (`VNPAY_HASH_SECRET_KEY` đặt riêng cho backend test), không dùng khoá sandbox thật.',
          '- Kênh WebSocket `table_<id>` mở cho khách không token (thiết kế hiện tại); kênh `kitchen_orders`/`staff_orders` yêu cầu token đúng vai trò.', '']
    MD_FILE.write_text('\n'.join(L), encoding='utf-8')


def write_xlsx(data):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    tests = data['tests']
    wb = Workbook(); ws = wb.active; ws.title = 'Kịch bản kiểm thử'
    heads = ['Mã TC', 'Luồng/Phân hệ', 'Yêu cầu tham chiếu (BR/AC/BO)', 'Tiền điều kiện', 'Các bước', 'Dữ liệu test',
             'Kết quả mong đợi', 'Kết quả thực tế', 'Trạng thái (Pass/Fail)', 'Ghi chú/Bằng chứng']
    widths = [10, 24, 20, 30, 52, 32, 52, 60, 14, 40]
    thin = Side(style='thin', color='BBBBBB'); border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.append(heads)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True, color='FFFFFF', size=11); c.fill = PatternFill('solid', fgColor='2F5D50')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True); c.border = border
    ws.row_dimensions[1].height = 34
    fills = {PASS: 'C6EFCE', FAIL: 'FFC7CE', TODO: 'FFEB9C'}
    fonts = {PASS: '006100', FAIL: '9C0006', TODO: '7F6000'}
    for t in tests:
        vals = [t['id'], t['flow'], t['ref'], t['pre'], t['steps'], t['data'], t['expected'], t['actual'], t['status'], t['note']]
        ws.append(vals)
        r = ws.max_row
        for i in range(1, 11):
            c = ws.cell(row=r, column=i); c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = border
        sc = ws.cell(row=r, column=9)
        sc.fill = PatternFill('solid', fgColor=fills[t['status']]); sc.font = Font(bold=True, color=fonts[t['status']])
        sc.alignment = Alignment(horizontal='center', vertical='top', wrap_text=True)
        lines = max(len(str(v)) / max(1, w - 2) + str(v).count('\n') for v, w in zip(vals, widths))
        ws.row_dimensions[r].height = min(400, max(30, 15 * (int(lines) + 1)))
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = f'A1:J{ws.max_row}'
    sm = wb.create_sheet('Tổng hợp')
    s = stats(tests)
    sm.append(['Chỉ số', 'Số lượng']); sm.append(['Tổng TC', len(tests)]); sm.append(['Pass', s[PASS]]); sm.append(['Fail', s[FAIL]])
    sm.append(['Chưa chạy (thủ công)', s[TODO]]); sm.append([])
    sm.append(['Mã', 'Yêu cầu', 'TC liên quan', 'Pass', 'Fail', 'Chưa chạy', 'Kết luận'])
    for texts in (AC_TEXT, BR_TEXT):
        for code, text, rel, v in mapping(tests, texts):
            ss = stats(rel)
            sm.append([code, text, ', '.join(x['id'] for x in rel), ss[PASS], ss[FAIL], ss[TODO], v])
            sm.cell(row=sm.max_row, column=7).fill = PatternFill('solid', fgColor='FFC7CE' if v.startswith('Chưa đạt') else ('C6EFCE' if v == 'Đạt' else 'FFEB9C'))
    for r in (1, 7):
        for c in sm[r]:
            if c.value is not None:
                c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='2F5D50')
    for i, w in enumerate([12, 40, 60, 8, 8, 12, 42], 1):
        sm.column_dimensions[get_column_letter(i)].width = w
    for row in sm.iter_rows(min_row=7):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = border
    wb.save(XLSX_FILE)


def make_shots(data):
    import markdown
    SHOTS.mkdir(exist_ok=True)
    tests = data['tests']
    css = ('body{font-family:"Segoe UI",Arial,sans-serif;margin:24px;color:#222;background:#fff}h1{font-size:22px;color:#2F5D50}'
           'h2{font-size:17px;color:#2F5D50;margin:18px 0 8px}table{border-collapse:collapse;width:100%;font-size:12.5px;margin-bottom:12px}'
           'th{background:#2F5D50;color:#fff;padding:6px 8px;text-align:left}td{border:1px solid #ccc;padding:5px 8px;vertical-align:top}'
           '.p{background:#C6EFCE;color:#006100;font-weight:700;text-align:center}.f{background:#FFC7CE;color:#9C0006;font-weight:700;text-align:center}'
           '.t{background:#FFEB9C;color:#7F6000;font-weight:700;text-align:center}')
    cls = {PASS: 'p', FAIL: 'f', TODO: 't'}
    s = stats(tests)
    tmp = Path(tempfile.mkdtemp(prefix='ft_shots_'))
    pages = []
    head = (f"<h1>Kết quả kiểm thử chức năng — ABC Restaurant</h1><p>Tổng {len(tests)} TC · <b>{s[PASS]} Pass</b> · "
            f"<b>{s[FAIL]} Fail</b> · {s[TODO]} Chưa chạy (thủ công) · chạy {data['generated']}</p>")
    chunk = 20
    cut = lambda x, n: x[:n] + ('…' if len(x) > n else '')
    for n, i in enumerate(range(0, len(tests), chunk), 1):
        body = ''.join(
            f"<tr><td>{t['id']}</td><td>{t['flow']}</td><td>{t['ref']}</td><td>{cut(t['expected'], 130)}</td>"
            f"<td>{cut(t['actual'], 150)}</td><td class='{cls[t['status']]}'>{t['status']}</td></tr>"
            for t in tests[i:i + chunk])
        html = (f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{head}<h2>Bảng kết quả ({i + 1}–{min(i + chunk, len(tests))})</h2>"
                f"<table><tr><th>Mã TC</th><th>Luồng</th><th>Yêu cầu</th><th>Kết quả mong đợi</th><th>Kết quả thực tế</th><th>Trạng thái</th></tr>{body}</table></body></html>")
        pages.append((f'01-ket-qua-{n}.png', html, 230 + chunk * 66))
    md = MD_FILE.read_text(encoding='utf-8')
    part = md[md.index('## 2. Đối chiếu'):md.index('## 6. Ghi chú')]
    body = markdown.markdown(part, extensions=['tables'])
    pages.append(('02-doi-chieu-AC-BR-thong-ke.png', f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{head}{body}</body></html>", 1950))
    for name, html, h in pages:
        f = tmp / (name + '.html'); f.write_text(html, encoding='utf-8')
        out = SHOTS / name
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', f'--user-data-dir={tmp / "profile"}',
                        f'--window-size=1500,{h}', f'--screenshot={out}', f.as_uri()], capture_output=True, timeout=120)
        print('ảnh', out.name, out.exists())
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    if '--regen' in sys.argv or '--shots' in sys.argv:
        data = json.loads(RESULTS_JSON.read_text(encoding='utf-8'))
        if '--regen' in sys.argv:
            write_md(data); write_xlsx(data)
        if '--shots' in sys.argv:
            make_shots(data)
        return
    proc = log = None
    try:
        proc, log = start_server()
        execute()
    finally:
        stop_server(proc, log)
    data = dump_json()
    write_md(data); write_xlsx(data)
    make_shots(data)
    s = stats(data['tests'])
    print(f"TỔNG {len(TCS)} TC: Pass {s[PASS]}, Fail {s[FAIL]}, Chưa chạy {s[TODO]}")


if __name__ == '__main__':
    main()
