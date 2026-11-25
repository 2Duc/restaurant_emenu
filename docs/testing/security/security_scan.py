"""Quét bảo mật cho ABC Restaurant — CHỈ chạy trên backend thử nghiệm local của chính dự án.

Cách chạy (từ thư mục gốc dự án), cần 1 backend riêng đã seed (seed_demo, seed_tables_promos, có admin_demo):
  backend/venv/Scripts/python.exe docs/testing/security/security_scan.py \
      --base http://127.0.0.1:8030 --base-vnpay http://127.0.0.1:8031 \
      --secret <DJANGO_SECRET_KEY của server thử> --vnpay-secret <HASH_SECRET giả của server vnpay> --out docs/testing/security

  --base        backend chế độ PAYMENT_GATEWAY_MODE=mock, DEBUG=0
  --base-vnpay  (tuỳ chọn) backend PAYMENT_GATEWAY_MODE=vnpay với khoá GIẢ, dùng cùng DB
Tài khoản: manager_demo / waiter_demo / kitchen_demo / admin_demo, mật khẩu --password (mặc định Demo@12345).
Kết quả: results.json, results.md (bảng), terminal.txt (log kiểu terminal) trong --out.
"""
import argparse, base64, hashlib, hmac, io, json, os, re, struct, sys, time, uuid, zlib
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[3]
ap = argparse.ArgumentParser()
ap.add_argument('--base', default='http://127.0.0.1:8030')
ap.add_argument('--base-vnpay', default='')
ap.add_argument('--password', default='Demo@12345')
ap.add_argument('--secret', default=os.environ.get('DJANGO_SECRET_KEY', ''))
ap.add_argument('--vnpay-secret', default='')
ap.add_argument('--out', default=str(Path(__file__).parent))
A = ap.parse_args()
BASE = A.base.rstrip('/')
API = BASE + '/api'
S = requests.Session()
TIMEOUT = 30
RESULTS, LOG = [], []
SEV_ORDER = {'Cao': 0, 'Trung bình': 1, 'Thấp': 2, 'Thông tin': 3, '-': 4}


def log(s=''):
    print(s)
    LOG.append(s)


def rec(id_, typ, payload, expected, actual, ok, severity='-', rec_='-'):
    """ok: True đạt / False không đạt / None thông tin."""
    sev = severity if ok is not True else '-'
    RESULTS.append(dict(id=id_, type=typ, payload=payload, expected=expected, actual=actual, ok=ok, severity=sev, rec=rec_))
    tag = {True: 'PASS', False: 'FAIL', None: 'INFO'}[ok]
    log(f'[{tag}] {id_:<9} {typ:<22} {actual[:110]}' + (f'  <{sev}>' if ok is False else ''))


def req(method, path, token=None, headers=None, base=API, noretry=False, **kw):
    h = dict(headers or {})
    if token:
        h['Authorization'] = 'Bearer ' + token
    try:
        for attempt in range(4):
            r = S.request(method, base + path if path.startswith('/') else path, headers=h, timeout=TIMEOUT, **kw)
            # throttle khách (theo bàn) có thể chạm giữa chừng khi quét hàng loạt: chờ rồi thử lại, trừ khi chính phép thử là throttle (noretry=True)
            if r.status_code == 429 and h.get('X-Table-Token') and not noretry and attempt < 3:
                time.sleep(float(r.headers.get('Retry-After', 5)) + 1)
                continue
            return r
    except requests.RequestException as e:
        class R:
            status_code = 0; text = 'ERR ' + str(e); headers = {}; content = b''
            def json(self): return {}
        return R()


def js(r):
    try:
        return r.json()
    except Exception:
        return None


def login(user):
    r = req('POST', '/auth/login/', json={'username': user, 'password': A.password})
    return (js(r) or {}).get('access'), (js(r) or {}).get('refresh'), r.status_code


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def forge(payload, secret=b'wrong-secret', alg='HS256'):
    head = b64u(json.dumps({'alg': alg, 'typ': 'JWT'}).encode())
    body = b64u(json.dumps(payload).encode())
    if alg == 'none':
        return f'{head}.{body}.'
    sig = hmac.new(secret, f'{head}.{body}'.encode(), hashlib.sha256).digest()
    return f'{head}.{body}.{b64u(sig)}'


def png_bytes():
    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    raw = zlib.compress(b'\x00\xff\x00\x00')
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', raw) + chunk(b'IEND', b'')


XSS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "';alert(document.cookie);//"]
SQLI = ["' OR 1=1--", "' OR '1'='1", "1; DROP TABLE api_order;--", "' UNION SELECT username,password,1 FROM api_useraccount--",
        "1' AND (SELECT 1 FROM pg_sleep(0))--", '" OR ""="']


def fresh_table(mgr):
    r = req('POST', '/tables/', mgr, json={'area': 'SEC', 'capacity': 2})
    return (js(r) or {}).get('id')


def has_leak(text):
    return bool(re.search(r'pbkdf2_sha256\$|api_useraccount|syntax error|psycopg|OperationalError|Traceback', text or ''))


def main():
    log(f'ABC Restaurant security scan  target={BASE}  {time.strftime("%Y-%m-%d %H:%M:%S")}')
    log('=' * 100)
    mgr, _, c1 = login('manager_demo'); wtr, wref, c2 = login('waiter_demo'); ktc, _, c3 = login('kitchen_demo'); adm, _, c4 = login('admin_demo')
    if not (mgr and wtr and ktc and adm):
        log(f'Không đăng nhập được tài khoản demo ({c1},{c2},{c3},{c4}) — có thể đang bị throttle, chờ 1 phút rồi chạy lại.')
        sys.exit(2)
    menu = js(req('GET', '/menu-items/')) or []
    mid = menu[0]['id']
    price = float(menu[0]['price'])
    TT = {}

    def table_token(t, mgr_tok=None):
        """Token phiên bàn như khách quét QR: quản lý đọc link QR (?k=) rồi POST /tables/session/ (cache theo bàn)."""
        if t in TT:
            return TT[t]
        q = js(req('GET', f'/tables/{t}/qr/', mgr_tok or mgr)) or {}
        k = re.search(r'[?&]k=([^&]+)', q.get('url', ''))
        r = req('POST', '/tables/session/', json={'table_id': t, 'k': k.group(1) if k else ''})
        TT[t] = (js(r) or {}).get('token', '')
        return TT[t]

    cust = lambda t: {'X-Table-Id': str(t), 'X-Table-Token': table_token(t)}
    created = {'menu': [], 'cat': [], 'user': []}

    # dữ liệu nền: 1 đơn bàn 1, 1 đơn bàn 2 (khách)
    o1 = js(req('POST', '/orders/', headers=cust(1), json={'table_id': 1, 'items': [{'menu_item_id': mid, 'quantity': 1, 'note': 'seed A'}]}))
    o2 = js(req('POST', '/orders/', headers=cust(2), json={'table_id': 2, 'items': [{'menu_item_id': mid, 'quantity': 1, 'note': 'seed B'}]}))
    o1id, o2id = o1['id'], o2['id']
    baseline = len(js(req('GET', '/orders/?limit=500', mgr)) or [])

    # ------------------------------------------------------------------ SQL Injection
    log('\n--- SQL Injection ---')
    bad = []
    leaks = []
    probes = [('GET', '/orders/', 'q', mgr), ('GET', '/orders/', 'table_id', mgr), ('GET', '/orders/', 'status', mgr), ('GET', '/orders/', 'date_from', mgr),
              ('GET', '/orders/', 'date_to', mgr), ('GET', '/orders/', 'limit', mgr), ('GET', '/menu-items/', 'search', None), ('GET', '/menu-items/', 'category', None),
              ('GET', '/menu-items/', 'ordering', None), ('GET', '/reviews/', 'order_id', mgr), ('GET', '/reviews/', 'menu_item', mgr), ('GET', '/reviews/', 'rating', mgr),
              ('GET', '/staff-calls/', 'status', wtr), ('GET', '/reports/summary/', 'date_from', mgr), ('GET', '/reports/summary/', 'period', mgr),
              ('GET', '/payments/', 'status', mgr), ('GET', '/audit-logs/', 'q', mgr), ('GET', '/users/', 'search', mgr)]
    for m, path, param, tok in probes:
        for p in SQLI:
            r = req(m, path, tok, params={param: p}, headers=cust(1))
            if r.status_code >= 500 or has_leak(r.text):
                bad.append(f'{path}?{param} -> {r.status_code}')
            elif path == '/orders/' and param in ('q', 'status', 'table_id') and r.status_code == 200 and len(r.json()) > baseline:
                bad.append(f'{path}?{param} trả nhiều hơn baseline')
    # nhóm theo endpoint để dễ đọc
    q500 = [b for b in bad]
    rec('SQLI-01', 'SQL Injection', f'{len(probes)} tham số x {len(SQLI)} payload (q, search, date_from, table_id, order_id, category, ...)',
        'Không 500, không lộ dữ liệu/SQL error', 'Sạch' if not q500 else f'{len(q500)} phản hồi 500 tại: ' + '; '.join(sorted(set(q500))), not q500, 'Thấp',
        'Ép kiểu/validate tham số lọc (table_id, order_id, category, rating, limit) bằng serializer/FilterSet; trả 400 thay vì 500.')
    r = req('GET', '/menu-items/', params={'search': "' UNION SELECT username,password,1 FROM api_useraccount--"})
    rec('SQLI-02', 'SQL Injection (UNION)', "GET /api/menu-items/?search=' UNION SELECT username,password,... FROM api_useraccount--",
        '200 danh sách rỗng, không lộ hash', f'HTTP {r.status_code}, {len(js(r) or [])} bản ghi, lộ hash: {has_leak(r.text)}',
        r.status_code == 200 and not has_leak(r.text) and len(js(r) or []) == 0, 'Cao', 'Dùng ORM tham số hoá (đang đúng).')
    codes = []
    for u in ("' OR 1=1--", "admin'--", 'admin" OR "1"="1'):
        for pw in ("' OR '1'='1", 'x'):
            r = req('POST', '/auth/login/', json={'username': u, 'password': pw}, headers={'X-Forwarded-For': f'10.9.{len(codes)}.1'})
            codes.append(r.status_code)
    rec('SQLI-03', 'SQL Injection (login)', "username=' OR 1=1--, admin'--; password=' OR '1'='1", '401/400, không 200/500',
        f'mã trả về: {sorted(set(codes))}', all(c in (400, 401) for c in codes), 'Cao', 'Giữ authenticate() của Django (tham số hoá).')
    codes = []
    for p in ["1 OR 1=1", "1'", "1;DROP TABLE api_order", "-1 UNION SELECT 1"]:
        for ep in ('/orders/%s/', '/menu-items/%s/', '/tables/%s/', '/payments/%s/'):
            codes.append(req('GET', ep % requests.utils.quote(p), mgr, headers=cust(1)).status_code)
    rec('SQLI-04', 'SQL Injection (path id)', "GET /api/orders|menu-items|tables|payments/<1 OR 1=1 | 1' | UNION...>/", '404 (không khớp route), không 500',
        f'mã: {sorted(set(codes))}', all(c in (404, 400) for c in codes), 'Thấp', 'Route dùng ký tự thường/số nguyên — đúng.')
    bodies = [('POST', '/orders/', cust(1), {'table_id': "1 OR 1=1", 'items': [{'menu_item_id': mid, 'quantity': 1}]}),
              ('POST', '/orders/', cust(1), {'table_id': 1, 'items': [{'menu_item_id': "1 OR 1=1", 'quantity': 1}]}),
              ('POST', '/orders/', cust(1), {'table_id': 1, 'items': [{'menu_item_id': mid, 'quantity': 1, 'note': "'); DROP TABLE api_order;--"}]}),
              ('POST', '/staff-calls/', cust(1), {'table': "1 OR 1=1", 'message': "' OR 1=1--"}),
              ('POST', '/reviews/', cust(1), {'order_item': "1 OR 1=1", 'rating': "5 OR 1=1", 'comment': "' OR 1=1--"}),
              ('POST', '/payments/create/', cust(1), {'order_id': "1 OR 1=1", 'method': "cash' OR 1=1--"}),
              ('POST', f'/orders/{o1id}/apply-promotion/', cust(1), {'code': "' OR 1=1--"})]
    codes = [(p, req(m, p, None, headers=h, json=b).status_code) for m, p, h, b in bodies]
    rec('SQLI-05', 'SQL Injection (body JSON)', "table_id/menu_item_id/rating/order_id/code = '1 OR 1=1', note='); DROP TABLE...",
        '400/403/404, không 500', f'{[c for _, c in codes]}', all(c < 500 for _, c in codes), 'Thấp', 'ReviewViewSet.create: validate order_item là số nguyên trước khi filter (trả 400 thay vì 500).')
    still = req('GET', f'/orders/{o1id}/', headers=cust(1)).status_code
    rec('SQLI-06', 'SQL Injection (DROP)', 'Sau mọi payload DROP TABLE, bảng api_order còn hoạt động', 'GET đơn vẫn 200', f'HTTP {still}', still == 200, 'Cao')

    # ------------------------------------------------------------------ XSS
    log('\n--- XSS ---')
    ids = {}
    # ghi chú món (khách)
    notes = []
    for x in XSS:
        r = req('POST', '/orders/', headers=cust(1), json={'table_id': 1, 'items': [{'menu_item_id': mid, 'quantity': 1, 'note': x}]})
        notes.append(r.status_code)
    od = req('GET', f'/orders/{o1id}/', headers=cust(1))
    ct = od.headers.get('Content-Type', '')
    stored = any(XSS[0][:20] in (i.get('note') or '') for i in (js(od) or {}).get('items', []))
    rec('XSS-01', 'XSS lưu trữ (ghi chú món)', ' | '.join(XSS[:2]), 'Lưu dạng text, API trả application/json (không render HTML)',
        f'POST {notes}; lưu raw={stored}; Content-Type={ct}', 'application/json' in ct, 'Trung bình', 'Giữ JSON; FE React escape tự động. Cân nhắc strip thẻ HTML phía server cho ghi chú.')
    ccat = req('POST', '/categories/', mgr, json={'name': XSS[1], 'description': XSS[0]})
    if ccat.status_code in (200, 201):
        created['cat'].append(js(ccat)['id'])
    cm = req('POST', '/menu-items/', mgr, data={'name': XSS[0], 'description': XSS[1], 'price': '1000', 'category': (js(ccat) or {}).get('id') or menu[0]['category']})
    if cm.status_code in (200, 201):
        created['menu'].append(js(cm)['id'])
    rl = req('GET', '/menu-items/', params={'search': 'alert'})
    rec('XSS-02', 'XSS lưu trữ (tên/mô tả món, tên danh mục)', f'name={XSS[0]} description={XSS[1]} category.name={XSS[1]}', 'API trả JSON text',
        f'tạo danh mục {ccat.status_code}, món {cm.status_code}; Content-Type={rl.headers.get("Content-Type")}', 'application/json' in rl.headers.get('Content-Type', ''), 'Trung bình',
        'Như trên; escape ở FE.')
    # đánh giá: cần món đã phục vụ + đơn đã hoàn tất (thanh toán tiền mặt) -> dùng bàn mới
    ft = fresh_table(mgr)
    ro = js(req('POST', '/orders/', headers=cust(ft), json={'table_id': ft, 'items': [{'menu_item_id': mid, 'quantity': 1}]})) or {}
    item = (ro.get('items') or [None])[0]
    rv = None
    if item:
        for tok, st in ((ktc, 'cooking'), (ktc, 'done'), (wtr, 'served')):
            req('PATCH', f"/order-items/{item['id']}/status/", tok, json={'status': st})
        pay = js(req('POST', '/payments/create/', headers=cust(ft), json={'order_id': ro['id'], 'method': 'cash'})) or {}
        req('POST', f"/payments/{pay.get('id', 0)}/confirm-cash/", wtr, json={})
        rv = req('POST', '/reviews/', headers=cust(ft), json={'order_item': item['id'], 'rating': 5, 'comment': XSS[1]})
    item = item or {'id': 1}
    rec('XSS-03', 'XSS lưu trữ (nhận xét đánh giá)', f'comment={XSS[1]}', 'Lưu text, trả JSON', f'POST /reviews/ -> {rv.status_code if rv is not None else "n/a"}; body={(rv.text if rv is not None else "")[:60]}',
        rv is not None and rv.status_code in (200, 201) and 'application/json' in rv.headers.get('Content-Type', ''), 'Trung bình')
    sc = req('POST', '/staff-calls/', headers=cust(3), json={'table': 3, 'message': XSS[0]})
    rec('XSS-04', 'XSS lưu trữ (gọi nhân viên)', f'message={XSS[0]}', 'Lưu text, trả JSON', f'HTTP {sc.status_code}; CT={sc.headers.get("Content-Type")}',
        sc.status_code in (200, 201) and 'application/json' in sc.headers.get('Content-Type', ''), 'Trung bình')
    br = req('GET', '/menu-items/', headers={'Accept': 'text/html'}, params={'search': 'alert'})
    raw_script = '<script>alert(1)</script>' in br.text
    rec('XSS-05', 'XSS phản chiếu (Browsable API)', 'GET /api/menu-items/ Accept: text/html chứa tên món <script>', 'HTML escape (&lt;script&gt;) hoặc không có Browsable API',
        f'HTTP {br.status_code}, CT={br.headers.get("Content-Type")}, script thô trong HTML={raw_script}, browsable={"Django REST framework" in br.text}', not raw_script,
        'Trung bình', 'Chỉ bật JSONRenderer ở production (DEFAULT_RENDERER_CLASSES) để tắt Browsable API.')
    if 'Django REST framework' in br.text:
        rec('XSS-06', 'Browsable API bật ở production', 'GET /api/ Accept: text/html', 'Tắt ở production', 'Browsable API đang trả HTML (lộ cấu trúc endpoint, form thử)', False, 'Thấp',
            "REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES']=('rest_framework.renderers.JSONRenderer',) khi DEBUG=0.")
    # FE grep
    pat = re.compile(r'dangerouslySetInnerHTML|\.innerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(')
    hits = []
    for f in (ROOT / 'frontend' / 'src').rglob('*'):
        if f.suffix in ('.js', '.jsx', '.ts', '.tsx') and f.is_file():
            for i, line in enumerate(f.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
                if pat.search(line):
                    hits.append(f'{f.relative_to(ROOT).as_posix()}:{i}')
    rec('XSS-07', 'XSS DOM (frontend)', 'grep dangerouslySetInnerHTML / innerHTML / eval / document.write trong frontend/src', 'Không có', 'Không thấy' if not hits else ', '.join(hits[:5]),
        not hits, 'Cao', 'Dùng JSX escape mặc định.')
    ls = any('localStorage' in f.read_text(encoding='utf-8', errors='ignore') and 'TOKEN' in f.read_text(encoding='utf-8', errors='ignore') for f in (ROOT / 'frontend' / 'src' / 'services').glob('*.js'))
    rec('XSS-08', 'Lưu JWT ở localStorage', 'frontend/src/services/api.js dùng localStorage cho access/refresh token', 'Token trong cookie HttpOnly (khuyến nghị)',
        'Token trong localStorage — nếu có XSS thì bị đánh cắp', None if ls else True, 'Thấp', 'Giữ CSP chặt; cân nhắc cookie HttpOnly+SameSite hoặc access token sống ngắn.')

    # ------------------------------------------------------------------ AuthZ
    log('\n--- Phân quyền / IDOR / JWT ---')
    admin_ep = [('GET', '/users/'), ('GET', '/audit-logs/'), ('GET', '/reports/summary/'), ('GET', '/payments/'), ('GET', '/orders/'), ('GET', '/staff-calls/'),
                ('POST', '/categories/'), ('POST', '/menu-items/'), ('POST', '/tables/'), ('DELETE', '/tables/1/'), ('POST', '/promotions/'), ('POST', '/users/'),
                ('PATCH', f'/orders/{o1id}/status/'), ('POST', '/payments/refund/'), ('POST', f'/payments/1/confirm-cash/'), ('PATCH', f"/order-items/{item['id']}/status/"),
                ('GET', '/tables/qr-codes/')]
    codes = {f'{m} {p}': req(m, p, None, json={}).status_code for m, p in admin_ep}
    okc = all(c in (401, 403) for c in codes.values())
    rec('AUTH-01', 'Truy cập không token', f'{len(admin_ep)} endpoint quản trị/nhân viên không Authorization', '401/403', f'sai: {[k for k, c in codes.items() if c not in (401, 403)] or "không"}', okc, 'Cao')
    low = {}
    for who, tok in (('PV', wtr), ('BEP', ktc)):
        for m, p in [('GET', '/users/'), ('GET', '/audit-logs/'), ('GET', '/reports/summary/'), ('GET', '/payments/'), ('POST', '/categories/'), ('POST', '/menu-items/'), ('POST', '/tables/'),
                     ('POST', '/promotions/'), ('POST', '/users/'), ('POST', '/payments/refund/')]:
            low[f'{who} {m} {p}'] = req(m, p, tok, json={}).status_code
    bad = [k for k, c in low.items() if c not in (401, 403)]
    rec('AUTH-02', 'Token role thấp (PV/BEP)', 'Phục vụ & Bếp gọi API chỉ QL/AD (users, reports, audit-logs, payments, tạo danh mục/món/bàn/khuyến mãi, refund)', '403', f'sai: {bad or "không"}', not bad, 'Cao')
    k = {'BEP GET /staff-calls/': req('GET', '/staff-calls/', ktc).status_code, 'BEP confirm-cash': req('POST', '/payments/1/confirm-cash/', ktc, json={}).status_code,
         'BEP PATCH order status': req('PATCH', f'/orders/{o1id}/status/', ktc, json={'status': 'cancelled'}).status_code}
    rec('AUTH-03', 'Token Bếp ngoài vai trò', 'Bếp: list staff-calls, xác nhận tiền mặt, đổi trạng thái đơn', '403', str(k), all(v == 403 for v in k.values()), 'Cao')
    # IDOR đơn
    t = {}
    t['order other table'] = req('GET', f'/orders/{o2id}/', headers=cust(1)).status_code
    t['order no header'] = req('GET', f'/orders/{o2id}/').status_code
    t['add-items other'] = req('POST', f'/orders/{o2id}/add-items/', headers=cust(1), json={'items': [{'menu_item_id': mid, 'quantity': 1}]}).status_code
    t['create order other table'] = req('POST', '/orders/', headers=cust(1), json={'table_id': 2, 'items': [{'menu_item_id': mid, 'quantity': 1}]}).status_code
    t['apply-promo other'] = req('POST', f'/orders/{o2id}/apply-promotion/', headers=cust(1), json={'code': 'ABC10'}).status_code
    t['cancel item other'] = req('POST', f"/order-items/{item['id']}/cancel/", headers=cust(1)).status_code
    t['staff-call other'] = req('POST', '/staff-calls/', headers=cust(1), json={'table': 2, 'message': 'x'}).status_code
    t['payment create other'] = req('POST', '/payments/create/', headers=cust(1), json={'order_id': o2id, 'method': 'cash'}).status_code
    pay2 = js(req('POST', '/payments/create/', headers=cust(2), json={'order_id': o2id, 'method': 'cash'})) or {}
    if pay2.get('id'):
        t['payment detail other'] = req('GET', f"/payments/{pay2['id']}/", headers=cust(1)).status_code
        t['payment sync other'] = req('POST', f"/payments/{pay2['id']}/sync/", headers=cust(1)).status_code
    t['reviews list other'] = len(js(req('GET', '/reviews/', headers=cust(1))) or [])
    bad = {k: v for k, v in t.items() if k != 'reviews list other' and v not in (401, 403, 404)}
    rec('AUTH-04', 'IDOR khách bàn A -> bàn B', 'Header X-Table-Id: 1 truy cập đơn/thanh toán/gọi NV/khuyến mãi/huỷ món của bàn 2', '403 cho mọi thao tác', f'sai: {bad or "không"}; chi tiết {t}', not bad, 'Cao')
    forged = [req('GET', f'/orders/{o2id}/', headers={'X-Table-Id': '2'}).status_code,
              req('GET', f'/orders/{o2id}/', headers={'X-Table-Token': 'abc'}).status_code,
              req('GET', f'/orders/{o2id}/', headers={'X-Table-Token': forge({'t': 2})}).status_code,
              req('POST', '/tables/session/', json={'table_id': 2, 'k': 'doan-bua'}).status_code,
              req('POST', '/payments/create/', headers={'X-Table-Id': '2'}, json={'order_id': o2id, 'method': 'cash'}).status_code]
    sp = req('GET', f'/orders/{o2id}/', headers={'X-Table-Id': '2'})
    rec('AUTH-05', 'IDOR giả mạo header bàn', f'Kẻ tấn công tự gửi X-Table-Id: 2 / X-Table-Token rác / token ký sai khoá / dò mã k, rồi GET /api/orders/{o2id}/ và POST thanh toán',
        '403 (cần token phiên bàn ký, lấy bằng mã k bí mật trong QR)', f'mã trả về {forged}', all(c in (401, 403) for c in forged), 'Trung bình',
        'Cấp token phiên bàn ký (QR chứa mã bí mật ngẫu nhiên, hết hạn theo phiên), kiểm tra token thay vì header X-Table-Id tự khai.')
    ids_seq = [req('GET', f'/orders/{i}/', headers=cust(2)).status_code for i in range(max(1, o2id - 2), o2id + 1)]
    rec('AUTH-06', 'ID tuần tự dễ đoán', 'Đơn/bàn/thanh toán dùng id số nguyên tăng dần', 'Khó đoán (UUID) hoặc có kiểm soát truy cập chặt', f'đơn {o2id-2}..{o2id}: {ids_seq}', None, 'Thấp',
        'Dùng mã đơn ngẫu nhiên (UUID/slug) hiển thị cho khách.')
    # leo thang
    me = js(req('GET', '/auth/me/', wtr)); uid = me['id']
    esc = req('PATCH', f'/users/{uid}/', wtr, json={'role': 'AD'}).status_code
    esc2 = req('PATCH', f'/users/{uid}/', wtr, json={'is_superuser': True, 'is_staff': True}).status_code
    mgr_me = js(req('GET', '/auth/me/', mgr))['id']
    esc3 = req('PATCH', f'/users/{mgr_me}/', mgr, json={'role': 'AD'}).status_code
    mk = req('POST', '/users/', mgr, json={'username': 'sec_probe_' + uuid.uuid4().hex[:6], 'role': 'AD', 'password': 'Zq!8vK2mPx9#'})
    if mk.status_code == 201:
        created['user'].append(js(mk)['id'])
    sup = req('POST', '/users/', mgr, json={'username': 'sec_probe_' + uuid.uuid4().hex[:6], 'role': 'PV', 'password': 'Zq!8vK2mPx9#', 'is_superuser': True})
    if sup.status_code == 201:
        created['user'].append(js(sup)['id'])
    is_su = (js(sup) or {}).get('is_superuser') if sup.status_code == 201 else False
    rec('AUTH-07', 'Leo thang vai trò', 'PV PATCH /users/<mình> {role:AD}; PV gửi is_superuser; QL tự nâng AD; QL tạo user AD; QL tạo user kèm is_superuser',
        '403/400, không tạo được AD/superuser', f'PV->AD {esc}, PV superuser {esc2}, QL tự->AD {esc3}, QL tạo AD {mk.status_code}, QL tạo is_superuser {sup.status_code}',
        esc in (401, 403) and esc2 in (401, 403) and esc3 in (400, 403) and mk.status_code in (400, 403) and not is_su, 'Cao')
    wk = req('POST', '/users/', mgr, json={'username': 'sec_probe_' + uuid.uuid4().hex[:6], 'role': 'PV', 'password': '1234'})
    if wk.status_code == 201:
        created['user'].append(js(wk)['id'])
    rec('AUTH-08', 'Mật khẩu yếu', 'Tạo nhân viên với password=1234', '400 (validator)', f'HTTP {wk.status_code}', wk.status_code == 400, 'Trung bình')
    lu = req('GET', '/users/', mgr)
    rec('AUTH-09', 'Lộ hash mật khẩu qua API', 'GET /api/users/ chứa trường password/hash', 'Không có', f'có "password" trong JSON: {"password" in lu.text}', 'password' not in lu.text, 'Cao')
    # JWT
    real = wtr
    payload = json.loads(b64d(real.split('.')[1]))
    now = int(time.time())
    j = {}
    j['sai khoá HS256'] = req('GET', '/auth/me/', forge(payload, b'attacker')).status_code
    j['alg none'] = req('GET', '/auth/me/', forge(payload, alg='none')).status_code
    hp, pp, sg = real.split('.')
    fake_p = dict(payload, role='AD', user_id=mgr_me)
    j['sửa payload giữ chữ ký'] = req('GET', '/auth/me/', f'{hp}.{b64u(json.dumps(fake_p).encode())}.{sg}').status_code
    j['rỗng chữ ký'] = req('GET', '/auth/me/', f'{hp}.{pp}.').status_code
    j['rác'] = req('GET', '/auth/me/', 'abc.def.ghi').status_code
    if A.secret:
        j['hết hạn (đúng khoá)'] = req('GET', '/auth/me/', forge(dict(payload, exp=now - 3600, iat=now - 7200), A.secret.encode())).status_code
        j['hợp lệ đúng khoá (đối chứng)'] = req('GET', '/auth/me/', forge(dict(payload, exp=now + 600), A.secret.encode())).status_code
        j['user_id không tồn tại'] = req('GET', '/auth/me/', forge(dict(payload, user_id=999999, exp=now + 600), A.secret.encode())).status_code
        j['token_type=refresh làm access'] = req('GET', '/auth/me/', forge(dict(payload, token_type='refresh', exp=now + 600), A.secret.encode())).status_code
    j['refresh làm access'] = req('GET', '/auth/me/', wref).status_code
    okj = all(v == 401 for k2, v in j.items() if 'đối chứng' not in k2) and (j.get('hợp lệ đúng khoá (đối chứng)', 200) == 200)
    rec('AUTH-10', 'JWT giả/hết hạn/alg none', 'sai khoá, alg=none, sửa role giữ chữ ký, hết hạn, user không tồn tại, refresh làm access', 'Tất cả 401 (đối chứng 200)', str(j), okj, 'Cao')
    nr = js(req('POST', '/auth/refresh/', json={'refresh': wref})) or {}
    again = req('POST', '/auth/refresh/', json={'refresh': wref}).status_code
    rec('AUTH-11', 'Refresh token xoay vòng', 'Dùng lại refresh token cũ sau khi đã xoay', '401 (blacklist)', f'lần 1 có access={bool(nr.get("access"))}, lần 2 -> {again}', bool(nr.get('access')) and again == 401, 'Trung bình')
    # WebSocket
    wsres = ws_checks(adm, o2id, mid, table_token, cust)
    for r in wsres:
        rec(*r)
    # giá/đặt hàng
    bt = fresh_table(mgr)
    po = js(req('POST', '/orders/', headers=cust(bt), json={'table_id': bt, 'items': [{'menu_item_id': mid, 'quantity': 2, 'unit_price': 1, 'price': 1, 'status': 'completed'}], 'total_amount': 1, 'status': 'completed'}))
    tot = float((po or {}).get('total_amount', -1))
    rec('BIZ-01', 'Thao túng giá/mass assignment', 'POST /orders/ kèm unit_price=1, total_amount=1, status=completed', 'Server bỏ qua, tính theo giá menu', f'tổng={tot} (kỳ vọng {price*2}); status={(po or {}).get("status")}',
        abs(tot - price * 2) < 1 and (po or {}).get('status') == 'pending', 'Cao')
    q = [req('POST', '/orders/', headers=cust(6), json={'table_id': 6, 'items': [{'menu_item_id': mid, 'quantity': v}]}).status_code for v in (0, -5, 1000)]
    rec('BIZ-02', 'Số lượng không hợp lệ', 'quantity = 0, -5, 1000', '400', str(q), all(c == 400 for c in q), 'Trung bình')
    rv2 = req('POST', '/reviews/', headers=cust(ft), json={'order_item': item['id'], 'rating': 99, 'comment': 'x'}).status_code
    rec('BIZ-03', 'Đánh giá ngoài khoảng', 'rating=99', '400', f'HTTP {rv2}', rv2 == 400, 'Thấp')
    # --------------------------------------------------------------- Bí mật / cấu hình
    log('\n--- Lộ bí mật / cấu hình ---')
    secrets_found = secret_scan()
    for r in secrets_found:
        rec(*r)
    # DEBUG / stacktrace
    bodies = [req('GET', '/orders/abc/', mgr), req('POST', '/orders/', data='{bad json', headers={'Content-Type': 'application/json', 'X-Table-Id': '1'}),
              req('GET', '/nonexistent/', base=BASE), req('GET', '/api/orders/?table_id=abc', mgr, base=BASE), req('GET', '/api/orders/?limit=999999999999999999999', mgr, base=BASE)]
    txt = ' '.join(b.text for b in bodies)
    dbg = bool(re.search(r"Traceback|Exception Value|You're seeing this error|DEBUG = True|settings\.py|site-packages", txt))
    rec('CFG-04', 'Lộ stacktrace (DEBUG)', 'Gây 404/400/lỗi tham số, đọc nội dung lỗi', 'Không có stacktrace/đường dẫn file', f'mã {[b.status_code for b in bodies]}; lộ stacktrace={dbg}', not dbg, 'Cao',
        'Chạy production với DJANGO_DEBUG=0.')
    r = req('GET', '/api/orders/?table_id=abc', mgr, base=BASE)
    rec('CFG-05', 'Xử lý tham số sai kiểu', 'GET /api/orders/?table_id=abc', '400, không phải 500', f'HTTP {r.status_code}', r.status_code == 400, 'Thấp', 'Validate table_id thành int trước khi filter.')
    r = req('GET', '/', base=BASE, headers={'Host': 'evil.example.com'})
    rec('CFG-06', 'Host header giả', 'Host: evil.example.com', '400 (ALLOWED_HOSTS)', f'HTTP {r.status_code}', r.status_code == 400, 'Trung bình', 'Giữ ALLOWED_HOSTS cụ thể.')
    r = req('GET', '/admin/login/', base=BASE)
    rec('CFG-07', 'Trang /admin/', 'GET /admin/login/', 'Không công khai hoặc có bảo vệ brute-force', f'HTTP {r.status_code} — trang đăng nhập admin công khai, không giới hạn thử mật khẩu', None if r.status_code == 200 else True,
        'Thấp', 'Đổi đường dẫn admin / chặn theo IP / thêm django-axes; bắt buộc mật khẩu mạnh.')
    # upload
    up = upload_checks(mgr, menu[0]['category'], created)
    for r in up:
        rec(*r)
    # CORS
    cors = {}
    for o in ('http://evil.example.com', 'null', 'http://localhost:5173'):
        r = req('OPTIONS', '/menu-items/', headers={'Origin': o, 'Access-Control-Request-Method': 'GET'})
        cors[o] = (r.headers.get('Access-Control-Allow-Origin'), r.headers.get('Access-Control-Allow-Credentials'))
    r = req('GET', '/menu-items/', headers={'Origin': 'http://evil.example.com'})
    rec('CFG-11', 'CORS origin lạ', 'Origin: http://evil.example.com / null (preflight + GET)', 'Không có Access-Control-Allow-Origin cho origin lạ; origin FE được phép',
        f'{cors}; GET origin lạ -> ACAO={r.headers.get("Access-Control-Allow-Origin")}', cors['http://evil.example.com'][0] is None and cors['null'][0] is None and cors['http://localhost:5173'][0] == 'http://localhost:5173', 'Cao')
    # security headers
    r = req('GET', '/menu-items/')
    h = r.headers
    miss = [x for x in ('X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy', 'Cross-Origin-Opener-Policy') if x not in h]
    rec('CFG-12', 'Header bảo mật', 'GET /api/menu-items/ — X-Frame-Options, X-Content-Type-Options, Referrer-Policy, COOP', 'Có đủ',
        f'X-Frame-Options={h.get("X-Frame-Options")}, nosniff={h.get("X-Content-Type-Options")}, Referrer-Policy={h.get("Referrer-Policy")}; thiếu: {miss or "không"}', not miss, 'Thấp')
    rx = req('GET', '/menu-items/', headers={'X-Forwarded-Proto': 'https'})
    hsts = rx.headers.get('Strict-Transport-Security')
    rec('CFG-13', 'HSTS / HTTPS', 'GET với X-Forwarded-Proto: https — Strict-Transport-Security; CSP; SECURE_SSL_REDIRECT', 'Có HSTS + CSP khi chạy https', f'HSTS={hsts}; CSP={rx.headers.get("Content-Security-Policy")}',
        bool(hsts), 'Thấp', 'Đặt SECURE_HSTS_SECONDS (>=31536000), SECURE_SSL_REDIRECT=True khi deploy HTTPS; thêm CSP ở frontend host (nginx/Vercel).')
    # IPN / mock-callback
    vn = A.base_vnpay.rstrip('/') if A.base_vnpay else ''
    vb = (vn + '/api') if vn else API
    mc = req('POST', '/payments/mock-callback/', base=vb, json={'txn_ref': 'x', 'result': 'bogus'})
    rec('PAY-01', 'mock-callback ở chế độ vnpay', f'POST {vb}/payments/mock-callback/ (server PAYMENT_GATEWAY_MODE=vnpay)', '404', f'HTTP {mc.status_code}' + ('' if vn else ' (CHƯA có server vnpay — kiểm tra trên server mock)'),
        mc.status_code == 404 if vn else None, 'Cao', 'Production bắt buộc đặt PAYMENT_GATEWAY_MODE=vnpay + khoá VNPay; mặc định "mock" khi thiếu khoá là nguy hiểm — nên fail-closed khi DEBUG=0.')
    mt = fresh_table(mgr)
    mo = js(req('POST', '/orders/', headers=cust(mt), json={'table_id': mt, 'items': [{'menu_item_id': mid, 'quantity': 1}]})) or {}
    mp = js(req('POST', '/payments/create/', headers=cust(mt), json={'order_id': mo.get('id', 0), 'method': 'vnpay'})) or {}
    mc2 = req('POST', '/payments/mock-callback/', base=API, json={'txn_ref': mp.get('transaction_id', 'x'), 'result': 'success'})
    mst = (js(req('GET', f"/orders/{mo.get('id', 0)}/", headers=cust(mt))) or {}).get('status')
    rec('PAY-02', 'mock-callback ở chế độ mock', 'Server mock: khách không token POST /payments/mock-callback/ {txn_ref, result:success} cho giao dịch chờ thanh toán', 'Chỉ dùng demo; production phải tắt',
        f'HTTP {mc2.status_code}; đơn chuyển sang "{mst}" mà không trả tiền (hợp lệ ở mock, NGUY HIỂM nếu lọt lên production)', None, 'Trung bình',
        'Không bao giờ chạy mock ở production; thêm kiểm tra settings.DEBUG hoặc biến ALLOW_MOCK_GATEWAY=1.')
    pc = req('POST', '/payments/create/', base=vb, headers=cust(7), json={'order_id': (js(req('POST', '/orders/', base=vb, headers=cust(7), json={'table_id': 7, 'items': [{'menu_item_id': mid, 'quantity': 1}]})) or {}).get('id', 0), 'method': 'vnpay'})
    pj = js(pc) or {}
    tx = pj.get('transaction_id', 'NOPE')
    params = {'vnp_TmnCode': 'WRONG', 'vnp_TxnRef': tx, 'vnp_Amount': '100', 'vnp_ResponseCode': '00', 'vnp_TransactionStatus': '00', 'vnp_SecureHash': 'deadbeef'}
    ipn = js(req('GET', '/payments/vnpay-ipn/', base=vb, params=params)) or {}
    ipn2 = js(req('GET', '/payments/vnpay-ipn/', base=vb, params={k: v for k, v in params.items() if k != 'vnp_SecureHash'})) or {}
    status_after = (js(req('GET', f"/payments/{pj.get('id')}/", base=vb, headers=cust(7))) or {}).get('status') if pj.get('id') else 'n/a'
    rec('PAY-03', 'IPN chữ ký sai', 'GET /payments/vnpay-ipn/ với vnp_SecureHash=deadbeef, ResponseCode=00 (và thiếu chữ ký)', 'RspCode 97, trạng thái giao dịch không đổi',
        f'{ipn}; thiếu chữ ký {ipn2}; payment sau đó={status_after}', ipn.get('RspCode') == '97' and ipn2.get('RspCode') == '97' and status_after == 'pending', 'Cao')
    if A.vnpay_secret and pj.get('id'):
        def sign(p):
            q = '&'.join(f'{k}={requests.utils.quote(str(v), safe="").replace("%20", "+")}' for k, v in sorted(p.items()))
            return hmac.new(A.vnpay_secret.encode(), q.encode(), hashlib.sha512).hexdigest()
        p2 = {'vnp_TmnCode': os.environ.get('VNPAY_TMN_CODE_FAKE', 'SECTEST'), 'vnp_TxnRef': tx, 'vnp_Amount': '100', 'vnp_ResponseCode': '00', 'vnp_TransactionStatus': '00'}
        p2['vnp_SecureHash'] = sign(p2)
        ipn3 = js(req('GET', '/payments/vnpay-ipn/', base=vb, params=p2)) or {}
        st2 = (js(req('GET', f"/payments/{pj.get('id')}/", base=vb, headers=cust(7))) or {}).get('status')
        rec('PAY-04', 'IPN chữ ký đúng nhưng sai số tiền', 'IPN ký bằng khoá giả của server thử, vnp_Amount=100 (sai)', 'RspCode 04, không ghi nhận thanh toán', f'{ipn3}; payment={st2}',
            ipn3.get('RspCode') == '04' and st2 == 'pending', 'Cao')
    vr = req('GET', '/payments/vnpay-return/', base=vb, params=params, allow_redirects=False)
    st3 = (js(req('GET', f"/payments/{pj.get('id')}/", base=vb, headers=cust(7))) or {}).get('status') if pj.get('id') else 'n/a'
    rec('PAY-05', 'vnpay-return chữ ký sai', 'GET /payments/vnpay-return/ chữ ký giả', 'Không đổi trạng thái giao dịch', f'HTTP {vr.status_code}; payment={st3}', st3 in ('pending', 'n/a'), 'Cao')
    cc = req('POST', f"/payments/{pj.get('id', 1)}/confirm-cash/", headers=cust(7), json={}).status_code
    rec('PAY-06', 'Khách tự xác nhận tiền mặt', 'Khách (không token) POST /payments/<id>/confirm-cash/', '401/403', f'HTTP {cc}', cc in (401, 403), 'Cao')
    # rate limit login (cuối cùng)
    log('\n--- Giới hạn tần suất ---')
    xs = [req('POST', '/auth/login/', json={'username': 'nobody', 'password': 'bad'}, headers={'X-Forwarded-For': f'203.0.113.{i}'}).status_code for i in range(25)]
    rec('RATE-01', 'Brute-force login (giả X-Forwarded-For)', '25 lần đăng nhập sai, mỗi lần X-Forwarded-For khác nhau', '429 sau 10 lần/phút (theo IP thật)', f'429 xuất hiện: {429 in xs}; mã: {sorted(set(xs))}',
        429 in xs, 'Cao', 'Đặt REST_FRAMEWORK NUM_PROXIES đúng số proxy tin cậy (hiện None => DRF tin X-Forwarded-For do client gửi, bypass throttle); thêm khoá theo username (django-axes).')
    ys = [req('POST', '/auth/login/', json={'username': 'nobody', 'password': 'bad'}).status_code for i in range(16)]
    rec('RATE-02', 'Giới hạn đăng nhập theo IP', '16 lần đăng nhập sai liên tiếp (không giả IP)', '429 sau 10 lần', f'429: {429 in ys}; mã: {sorted(set(ys))}', 429 in ys, 'Trung bình')
    rt = fresh_table(mgr)
    rh = cust(rt)
    zs = [req('POST', '/orders/', headers=rh, noretry=True, json={'table_id': rt, 'items': [{'menu_item_id': mid, 'quantity': 1}]}).status_code for _ in range(30)]
    cs = [req('POST', '/staff-calls/', headers=rh, noretry=True, json={'table': rt, 'message': 'rate'}).status_code for _ in range(10)]
    gs = [req('GET', f'/tables/{rt}/current-order/', headers=rh, noretry=True).status_code for _ in range(140)]
    rec('RATE-03', 'Giới hạn API khách', f'bàn mới: 30 POST /orders/, 10 POST /staff-calls/, 140 GET current-order liên tiếp (throttle theo bàn: order_create 20/min, staff_call 6/min, customer 120/min)', '429 khi vượt',
        f'429 — orders: {429 in zs}, staff-calls: {429 in cs}, customer: {429 in gs}', 429 in zs and 429 in cs and 429 in gs, 'Trung bình',
        'Gắn throttle (AnonRateThrottle/ScopedRateThrottle) cho POST /orders/, /staff-calls/, /reviews/, /payments/create/ và đặt giới hạn ở reverse proxy.')
    cleanup(created, mgr, adm)
    finish()


def ws_checks(adm, o2id, mid, table_token, cust):
    out = []
    try:
        import asyncio, websockets
    except ImportError:
        return [('WS-01', 'WebSocket', 'thiếu thư viện websockets', '-', 'bỏ qua', None, '-', '-')]
    host = BASE.replace('http://', '')

    async def run():
        r = {}
        for name, path, tok in (('kitchen không token', 'kitchen_orders', None), ('staff không token', 'staff_orders', None), ('kitchen token giả', 'kitchen_orders', 'abc.def.ghi')):
            try:
                async with websockets.connect(f'ws://{host}/ws/{path}/' + (f'?token={tok}' if tok else ''), open_timeout=10) as ws:
                    try:
                        await asyncio.wait_for(ws.recv(), 2); r[name] = 'MỞ+nhận dữ liệu'
                    except asyncio.TimeoutError:
                        r[name] = 'MỞ (kết nối được)'
                    except Exception as e:
                        r[name] = 'đóng ' + str(getattr(e, 'code', ''))
            except Exception as e:
                r[name] = 'từ chối (' + type(e).__name__ + ')'
        got = []
        t1tok, t2tok = table_token(1), table_token(2)
        for name, tok in (('không token', None), ('token rác', 'abc'), ('token bàn 1', t1tok)):   # kẻ lạ nghe bàn 2
            try:
                async with websockets.connect(f'ws://{host}/ws/table_2/' + (f'?token={tok}' if tok else ''), open_timeout=10) as ws:
                    await asyncio.sleep(0.5)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, lambda: req('POST', '/orders/', headers=cust(2), json={'table_id': 2, 'items': [{'menu_item_id': mid, 'quantity': 1, 'note': 'WS-PROBE'}]}))
                    try:
                        got.append(json.loads(await asyncio.wait_for(ws.recv(), 5)))
                    except Exception:
                        pass
                    r['table_2 ' + name] = 'MỞ'
            except Exception as e:
                r['table_2 ' + name] = 'từ chối (' + type(e).__name__ + ')'
        try:   # đối chứng: token đúng bàn 2 phải vào được
            async with websockets.connect(f'ws://{host}/ws/table_2/?token={t2tok}', open_timeout=10):
                r['table_2 token đúng'] = 'MỞ'
        except Exception as e:
            r['table_2 token đúng'] = 'từ chối (' + type(e).__name__ + ')'
        r['leak'] = bool(got and got[0].get('type') == 'new_order')
        r['leak_fields'] = sorted((got[0].get('order') or {}).keys())[:6] if r['leak'] else []
        return r
    r = asyncio.run(run())
    privs = [r.get(k, '') for k in ('kitchen không token', 'staff không token', 'kitchen token giả')]
    out.append(('WS-01', 'WebSocket phân quyền', 'Kết nối ws/kitchen_orders/, ws/staff_orders/ không token / token giả', 'Bị đóng (4403)', str({k: r.get(k) for k in ('kitchen không token', 'staff không token', 'kitchen token giả')}),
                all('MỞ' not in p for p in privs), 'Cao'))
    wsd = {k: v for k, v in r.items() if k.startswith('table_2')}
    out.append(('WS-02', 'WebSocket IDOR (kênh bàn)', 'Kết nối ws/table_2/ không token / token rác / token bàn 1 rồi bàn 2 đặt món; đối chứng token đúng bàn 2', 'Chỉ token đúng bàn được vào; không nhận dữ liệu đơn bàn khác', f'{wsd}; nhận new_order của bàn 2 khi chưa xác thực: {r["leak"]}',
                (not r['leak']) and all('MỞ' not in wsd.get('table_2 ' + n, '') for n in ('không token', 'token rác', 'token bàn 1')) and 'MỞ' in wsd.get('table_2 token đúng', ''),
                'Trung bình', 'Xác thực kênh table_<id> bằng token phiên bàn (ký) hoặc chỉ gửi sự kiện tối thiểu (không kèm ghi chú/giá).'))
    return out


def secret_scan():
    out = []
    env = {}
    ef = ROOT / 'backend' / '.env'
    if ef.exists():
        for line in ef.read_text(encoding='utf-8', errors='ignore').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    sens = {k: v for k, v in env.items() if v and any(w in k for w in ('SECRET', 'PASSWORD', 'HASH', 'TMN_CODE')) and len(v) >= 6}
    hits = []
    scanned = 0
    for d in ('frontend/dist', 'frontend/src', 'frontend/public'):
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob('*'):
            if f.is_file() and f.stat().st_size < 8_000_000:
                scanned += 1
                try:
                    t = f.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                for k, v in sens.items():
                    if v in t:
                        hits.append(f'{k} trong {f.relative_to(ROOT).as_posix()}')
                if re.search(r'VNPAY_HASH_SECRET|DJANGO_SECRET_KEY', t):
                    hits.append(f'tên biến bí mật trong {f.relative_to(ROOT).as_posix()}')
    out.append(('SEC-01', 'Lộ bí mật trong frontend', f'Tìm giá trị thật của {", ".join(sorted(sens))} + tên VNPAY_HASH_SECRET/DJANGO_SECRET_KEY trong frontend/dist, src, public ({scanned} file)',
                'Không có', 'Không thấy' if not hits else '; '.join(sorted(set(hits))[:5]), not hits, 'Cao', 'Chỉ đưa biến VITE_* công khai vào bundle.'))
    ign = {}
    for rel in ('.gitignore', 'backend/.gitignore', 'backend/.dockerignore', 'frontend/.dockerignore', '.dockerignore'):
        p = ROOT / rel
        ign[rel] = (re.search(r'^\s*\.env', p.read_text(encoding='utf-8', errors='ignore'), re.M) is not None) if p.exists() else None
    docker_ok = ign.get('backend/.dockerignore') is True
    git_ok = ign.get('.gitignore') is True or ign.get('backend/.gitignore') is True
    out.append(('SEC-02', 'backend/.env bị đóng gói/commit', 'Kiểm tra .gitignore / .dockerignore có loại .env', 'Có ở .gitignore và backend/.dockerignore',
                f'{ign}', docker_ok and git_ok, 'Trung bình' if docker_ok else 'Cao',
                'Thêm .gitignore ở thư mục gốc & backend/ với dòng ".env"; .env chứa mật khẩu DB và khoá VNPay.'))
    served = []
    for p in ('/.env', '/media/../.env', '/media/%2e%2e/.env', '/media/..%2f.env', '/static/.env', '/static/../.env', '/media/../manage.py', '/media/../db.sqlite3', '/media/%2e%2e/backend/settings.py'):
        r = req('GET', p, base=BASE)
        if r.status_code == 200 and ('SECRET' in r.text or 'DB_PASSWORD' in r.text or 'INSTALLED_APPS' in r.text or 'import ' in r.text[:200] or r.content[:6] == b'SQLite'):
            served.append(p)
    out.append(('SEC-03', 'Path traversal lấy .env / mã nguồn', 'GET /media/../.env, /media/%2e%2e/.env, /static/../.env, /media/../db.sqlite3 ...', '404, không trả file', 'Không lộ' if not served else f'LỘ: {served}', not served, 'Cao'))
    st = (ROOT / 'backend' / 'backend' / 'settings.py').read_text(encoding='utf-8', errors='ignore')
    devkey = re.search(r"_DEV_KEY\s*=\s*['\"]([^'\"]+)['\"]", st)
    key = env.get('DJANGO_SECRET_KEY', '')
    is_default = bool(devkey and key == devkey.group(1))
    out.append(('SEC-04', 'SECRET_KEY mặc định/yếu', 'settings: DEBUG=0 mà SECRET_KEY = _DEV_KEY => ImproperlyConfigured; so sánh khoá trong .env với khoá dev', 'Khoá riêng, >= 50 ký tự, fail-closed khi DEBUG=0',
                f'fail-closed khi DEBUG=0: {"ImproperlyConfigured" in st}; .env dùng khoá dev: {is_default}; độ dài khoá .env: {len(key)}', ('ImproperlyConfigured' in st) and not is_default and len(key) >= 50, 'Cao',
                'Sinh khoá mới bằng get_random_secret_key() cho production.'))
    dbg = env.get('DJANGO_DEBUG') == '1'
    out.append(('SEC-05', 'DEBUG bật trong .env', 'backend/.env: DJANGO_DEBUG', '0 khi triển khai', f'.env máy dev đặt DJANGO_DEBUG={env.get("DJANGO_DEBUG")} (chấp nhận khi chạy local; server quét chạy DEBUG=0)', None if dbg else True, 'Thấp',
                'Không dùng .env dev cho production.'))
    return out


def upload_checks(mgr, cat, created):
    out = []
    cases = [('shell.html', b'<html><script>alert(1)</script></html>', 'text/html'), ('x.svg', b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script></svg>', 'image/svg+xml'),
             ('shell.php', b'<?php system($_GET["c"]); ?>', 'image/png'), ('shell.php.png', b'<?php system($_GET["c"]); ?>', 'image/png'),
             ('real.php', png_bytes(), 'image/png'), ('poly.png', png_bytes() + b'<?php system($_GET["c"]); ?><script>alert(1)</script>', 'image/png')]
    res = {}
    paths = {}
    for name, data, ctype in cases:
        r = req('POST', '/menu-items/', mgr, data={'name': 'UPLOAD_' + name, 'price': '1000', 'category': cat}, files={'image_url': (name, data, ctype)})
        res[name] = r.status_code
        if r.status_code in (200, 201):
            d = js(r) or {}
            created['menu'].append(d.get('id'))
            paths[name] = d.get('image_url')
    bad = [n for n in ('shell.html', 'x.svg', 'shell.php', 'shell.php.png', 'real.php') if res.get(n) in (200, 201)]
    out.append(('CFG-08', 'Upload file độc (html/svg/php)', 'Tải lên image_url: shell.html, x.svg (script), shell.php (image/png), shell.php.png, real.php (PNG hợp lệ tên .php)', '400 (chỉ ảnh hợp lệ)',
                f'{res}', not bad, 'Cao', 'ImageField + Pillow đang chặn; giữ nguyên, thêm danh sách phần mở rộng cho phép.'))
    if 'poly.png' in paths and paths['poly.png']:
        u = paths['poly.png']
        r = req('GET', u if u.startswith('http') else BASE + u, base='')
        ctype = r.headers.get('Content-Type', '')
        out.append(('CFG-09', 'Polyglot ảnh + mã', 'PNG hợp lệ + nối <?php ... ?> / <script> (poly.png)', 'Phục vụ đúng image/png, nosniff, không thực thi', f'tải lên {res["poly.png"]}; phục vụ Content-Type={ctype}; nosniff={r.headers.get("X-Content-Type-Options")}',
                    ctype == 'image/png' and r.headers.get('X-Content-Type-Options') == 'nosniff', 'Thấp', 'Phục vụ media qua CDN/nginx với nosniff; hệ thống không thực thi PHP nên rủi ro thấp; có thể re-encode ảnh khi upload.'))
    else:
        out.append(('CFG-09', 'Polyglot ảnh + mã', 'poly.png', 'Từ chối hoặc phục vụ an toàn', f'upload {res.get("poly.png")}', True, '-'))
    big = req('POST', '/menu-items/', mgr, data={'name': 'UPLOAD_big', 'price': '1000', 'category': cat}, files={'image_url': ('big.png', png_bytes() + b'0' * (6 * 1024 * 1024), 'image/png')})
    if big.status_code in (200, 201):
        created['menu'].append(js(big)['id'])
    out.append(('CFG-10', 'Upload quá dung lượng', 'PNG > 5MB', '400', f'HTTP {big.status_code}', big.status_code == 400, 'Thấp', 'Serializer đã giới hạn 5MB.'))
    return out


def cleanup(created, mgr, adm):
    for i in created['menu']:
        if i:
            req('DELETE', f'/menu-items/{i}/', mgr)
    for i in created['cat']:
        req('DELETE', f'/categories/{i}/', mgr)
    for i in created['user']:
        req('PATCH', f'/users/{i}/', adm, json={'is_active': False})


def finish():
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    npass = sum(1 for r in RESULTS if r['ok'] is True); nfail = sum(1 for r in RESULTS if r['ok'] is False); ninfo = sum(1 for r in RESULTS if r['ok'] is None)
    log('=' * 100)
    log(f'TỔNG: {len(RESULTS)} kiểm tra | ĐẠT {npass} | KHÔNG ĐẠT {nfail} | THÔNG TIN {ninfo}')
    for r in sorted([r for r in RESULTS if r['ok'] is False], key=lambda r: SEV_ORDER.get(r['severity'], 9)):
        log(f'  [{r["severity"]:<10}] {r["id"]:<9} {r["type"]}')
    (out / 'results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'terminal.txt').write_text('\n'.join(LOG), encoding='utf-8')
    esc = lambda s: str(s).replace('|', '\\|').replace('\n', ' ')
    rows = ['| Mã | Loại lỗ hổng | Payload / cách thử | Kết quả mong đợi | Thực tế | Đạt/Không đạt | Mức độ | Khuyến nghị |', '|---|---|---|---|---|---|---|---|']
    for r in RESULTS:
        rows.append('| ' + ' | '.join([r['id'], esc(r['type']), esc(r['payload']), esc(r['expected']), esc(r['actual']),
                                       {True: 'Đạt', False: 'Không đạt', None: 'Thông tin'}[r['ok']], r['severity'] if r['ok'] is not True else '-', esc(r['rec']) if r['ok'] is not True else '-']) + ' |')
    (out / 'results.md').write_text('\n'.join(rows), encoding='utf-8')


if __name__ == '__main__':
    main()
