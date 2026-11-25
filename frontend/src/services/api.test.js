import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, clearTokens, connectSocket, ensureTableAccess, getRole, getTableToken, getUser, login, money, setTokens, startTableSession } from './api';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });

describe('money()', () => {
  it('formats integer VND with vi-VN grouping and currency sign', () => {
    // Định dạng 85000 -> "85.000 ₫"
    expect(money(85000)).toBe('85.000 ₫');
  });
  it('treats null, undefined, empty and NaN-like input as zero', () => {
    // Giá trị rỗng/không hợp lệ -> 0 ₫
    expect(money(null)).toBe('0 ₫');
    expect(money(undefined)).toBe('0 ₫');
    expect(money('')).toBe('0 ₫');
  });
  it('accepts numeric strings', () => {
    // Chuỗi số (Decimal từ API) vẫn được định dạng
    expect(money('1250000')).toBe('1.250.000 ₫');
  });
});

describe('role / user helpers', () => {
  beforeEach(() => localStorage.clear());
  it('getUser returns null when storage is empty or corrupt', () => {
    // Không có user hoặc JSON hỏng -> null, không ném lỗi
    expect(getUser()).toBeNull();
    localStorage.setItem('abc_user', '{bad');
    expect(getUser()).toBeNull();
  });
  it('getRole treats superuser as AD', () => {
    // Superuser Django được coi là AD ở giao diện
    localStorage.setItem('abc_user', JSON.stringify({ role: 'PV', is_superuser: true }));
    expect(getRole()).toBe('AD');
  });
  it('getRole returns the role of a normal user', () => {
    // User thường -> role của họ
    localStorage.setItem('abc_user', JSON.stringify({ role: 'BEP' }));
    expect(getRole()).toBe('BEP');
  });
  it('clearTokens removes tokens and user', () => {
    // Đăng xuất xoá toàn bộ token và user
    setTokens({ access: 'a', refresh: 'r' });
    localStorage.setItem('abc_user', '{}');
    clearTokens();
    expect(localStorage.length).toBe(0);
  });
});

describe('request error handling', () => {
  beforeEach(() => { localStorage.clear(); window.history.pushState({}, '', '/'); });
  afterEach(() => vi.restoreAllMocks());

  it('returns parsed JSON on success', async () => {
    // Phản hồi 200 -> trả về payload đã parse
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ok: 1 })));
    await expect(api.get('/x/')).resolves.toEqual({ ok: 1 });
  });
  it('throws the "detail" message from the server', async () => {
    // Lỗi 400 có detail -> Error(message = detail)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Bàn đang dọn' }, 400)));
    await expect(api.post('/orders/', {})).rejects.toThrow('Bàn đang dọn');
  });
  it('falls back to "message" then plain text then generic message', async () => {
    // Thứ tự dự phòng: message -> text thuần -> thông báo chung
    const f = vi.fn()
      .mockResolvedValueOnce(json({ message: 'M' }, 400))
      .mockResolvedValueOnce(new Response('plain error', { status: 500 }))
      .mockResolvedValueOnce(json({}, 500));
    vi.stubGlobal('fetch', f);
    await expect(api.get('/a')).rejects.toThrow('M');
    await expect(api.get('/a')).rejects.toThrow('plain error');
    await expect(api.get('/a')).rejects.toThrow('Có lỗi xảy ra khi gọi API.');
  });
  it('returns null for an empty body', async () => {
    // Body rỗng (204) -> null
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })));
    await expect(api.delete('/x/1/')).resolves.toBeNull();
  });
  it('sends X-Table-Id from /table/<id> and Bearer token', async () => {
    // Header bàn lấy từ URL QR, token gắn Authorization
    window.history.pushState({}, '', '/table/7');
    setTokens({ access: 'tok' });
    const f = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal('fetch', f);
    await api.get('/menu-items/');
    const headers = f.mock.calls[0][1].headers;
    expect(headers.get('X-Table-Id')).toBe('7');
    expect(headers.get('Authorization')).toBe('Bearer tok');
  });
  it('reads legacy ?table= only on /menu and /payment-result', async () => {
    // Link cũ /menu?table=3 có header; trang khác thì không
    const f = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal('fetch', f);
    window.history.pushState({}, '', '/menu?table=3');
    await api.get('/a');
    expect(f.mock.calls[0][1].headers.get('X-Table-Id')).toBe('3');
    window.history.pushState({}, '', '/other?table=3');
    await api.get('/a');
    expect(f.mock.calls[1][1].headers.get('X-Table-Id')).toBeNull();
    window.history.pushState({}, '', '/menu?table=abc');
    await api.get('/a');
    expect(f.mock.calls[2][1].headers.get('X-Table-Id')).toBeNull();
  });
  it('sets JSON content type for body but not for FormData', async () => {
    // JSON có Content-Type; FormData để trình duyệt tự đặt
    const f = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal('fetch', f);
    await api.post('/a', { a: 1 });
    expect(f.mock.calls[0][1].headers.get('Content-Type')).toBe('application/json');
    await api.upload('/a', new FormData());
    expect(f.mock.calls[1][1].headers.get('Content-Type')).toBeNull();
  });
  it('refreshes the token on 401 and retries once', async () => {
    // 401 + có refresh -> gọi refresh, lưu token mới, gọi lại
    setTokens({ access: 'old', refresh: 'ref' });
    const f = vi.fn()
      .mockResolvedValueOnce(json({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(json({ access: 'new' }))
      .mockResolvedValueOnce(json({ ok: true }));
    vi.stubGlobal('fetch', f);
    await expect(api.get('/me/')).resolves.toEqual({ ok: true });
    expect(f).toHaveBeenCalledTimes(3);
    expect(f.mock.calls[2][1].headers.get('Authorization')).toBe('Bearer new');
    expect(localStorage.getItem('abc_access_token')).toBe('new');
  });
  it('clears tokens when refresh fails', async () => {
    // Refresh thất bại -> xoá token, ném lỗi của request gốc
    setTokens({ access: 'old', refresh: 'ref' });
    const f = vi.fn()
      .mockResolvedValueOnce(json({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(json({}, 401));
    vi.stubGlobal('fetch', f);
    await expect(api.get('/me/')).rejects.toThrow('expired');
    expect(localStorage.getItem('abc_access_token')).toBeNull();
  });
  it('login stores tokens and user', async () => {
    // login lưu token + user vào localStorage
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ access: 'a', refresh: 'r', user: { role: 'QL' } })));
    await login('u', 'p');
    expect(getRole()).toBe('QL');
    expect(localStorage.getItem('abc_refresh_token')).toBe('r');
  });
});

describe('connectSocket reconnect', () => {
  let sockets;
  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    vi.stubGlobal('WebSocket', class {
      constructor(url) { this.url = url; this.close = vi.fn(); sockets.push(this); }
    });
    localStorage.clear();
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('opens a socket for the group, including token when logged in', () => {
    // URL có /ws/<group>/ và ?token= khi đã đăng nhập
    setTokens({ access: 'a b' });
    connectSocket('staff_orders');
    expect(sockets[0].url).toBe('ws://127.0.0.1:8000/ws/staff_orders/?token=a%20b');
  });
  it('reconnects with backoff 1s, 2s, 5s, 10s, 10s', () => {
    // Mất kết nối liên tục -> thử lại sau 1s, 2s, 5s, 10s rồi giữ 10s
    connectSocket('g');
    for (const [i, delay] of [1000, 2000, 5000, 10000, 10000].entries()) {
      expect(sockets).toHaveLength(i + 1);
      sockets[i].onclose();
      vi.advanceTimersByTime(delay - 1);
      expect(sockets).toHaveLength(i + 1);
      vi.advanceTimersByTime(1);
      expect(sockets).toHaveLength(i + 2);
    }
  });
  it('resets the backoff after a successful open', () => {
    // onopen đặt lại bộ đếm -> lần mất kết nối kế tiếp chờ 1s
    const onOpen = vi.fn();
    connectSocket('g', { onOpen });
    sockets[0].onclose(); vi.advanceTimersByTime(1000);
    sockets[1].onclose(); vi.advanceTimersByTime(2000);
    sockets[2].onopen();
    expect(onOpen).toHaveBeenCalled();
    sockets[2].onclose(); vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(4);
  });
  it('forwards messages and close events to handlers', () => {
    // onMessage/onClose được gọi với dữ liệu tương ứng
    const onMessage = vi.fn(); const onClose = vi.fn();
    connectSocket('g', { onMessage, onClose });
    sockets[0].onmessage({ data: 'x' });
    sockets[0].onclose();
    expect(onMessage).toHaveBeenCalledWith({ data: 'x' });
    expect(onClose).toHaveBeenCalled();
  });
  it('stops reconnecting after the returned close function is called', () => {
    // Gọi hàm đóng -> đóng socket, huỷ timer, không nối lại
    const stop = connectSocket('g');
    const first = sockets[0];
    stop();
    expect(first.close).toHaveBeenCalled();
    vi.advanceTimersByTime(60000);
    expect(sockets).toHaveLength(1);
  });
  it('cancels a pending reconnect timer on close', () => {
    // Đóng khi đang chờ nối lại -> không tạo socket mới
    const stop = connectSocket('g');
    sockets[0].onclose();
    stop();
    vi.advanceTimersByTime(60000);
    expect(sockets).toHaveLength(1);
  });
  it('retries when the WebSocket constructor throws', () => {
    // Constructor ném lỗi -> vẫn lên lịch thử lại
    let calls = 0;
    vi.stubGlobal('WebSocket', class { constructor() { calls++; if (calls === 1) throw new Error('boom'); sockets.push(this); this.close = vi.fn(); } });
    connectSocket('g');
    expect(sockets).toHaveLength(0);
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(1);
  });
});

describe('table session token (AUTH-05)', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); window.history.pushState({}, '', '/'); });
  afterEach(() => vi.restoreAllMocks());

  it('startTableSession posts table_id + k and stores the token per table', async () => {
    // Đổi (table_id, k) lấy token, lưu sessionStorage theo bàn
    const f = vi.fn().mockResolvedValue(json({ token: 'T7', table_id: 7, expires_in: 21600 }));
    vi.stubGlobal('fetch', f);
    await startTableSession('7', 'secret');
    expect(f.mock.calls[0][0]).toMatch(/\/tables\/session\/$/);
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ table_id: 7, k: 'secret' });
    expect(getTableToken('7')).toBe('T7');
    expect(getTableToken('8')).toBeNull();
  });
  it('ignores expired stored tokens', () => {
    // Token quá hạn không được dùng
    sessionStorage.setItem('abc_table_session_3', JSON.stringify({ token: 'old', exp: Date.now() - 1 }));
    expect(getTableToken('3')).toBeNull();
    sessionStorage.setItem('abc_table_session_3', '{bad');
    expect(getTableToken('3')).toBeNull();
  });
  it('sends X-Table-Token (and X-Table-Id for logging) once a session exists', async () => {
    // Mọi yêu cầu trên /table/<id> gửi kèm X-Table-Token
    sessionStorage.setItem('abc_table_session_7', JSON.stringify({ token: 'T7', exp: Date.now() + 60000 }));
    window.history.pushState({}, '', '/table/7');
    const f = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal('fetch', f);
    await api.get('/orders/1/');
    const h = f.mock.calls[0][1].headers;
    expect(h.get('X-Table-Token')).toBe('T7');
    expect(h.get('X-Table-Id')).toBe('7');
  });
  it('keeps the token for /payment-result?table=<id> (VNPay return)', async () => {
    // Quay về từ VNPay: token vẫn nằm trong sessionStorage nên API khách còn hoạt động
    sessionStorage.setItem('abc_table_session_12', JSON.stringify({ token: 'T12', exp: Date.now() + 60000 }));
    window.history.pushState({}, '', '/payment-result?status=success&order=5&table=12');
    const f = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal('fetch', f);
    await api.get('/orders/5/');
    expect(f.mock.calls[0][1].headers.get('X-Table-Token')).toBe('T12');
  });
  it('ensureTableAccess: with k exchanges, without k reuses, failure returns false', async () => {
    // Có k -> đổi token; không k -> dùng token đã lưu; k sai -> false và xoá token cũ
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ token: 'T1', expires_in: 100 })));
    await expect(ensureTableAccess('1', 'good')).resolves.toBe(true);
    await expect(ensureTableAccess('1', null)).resolves.toBe(true);
    await expect(ensureTableAccess('2', null)).resolves.toBe(false);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'bad' }, 403)));
    await expect(ensureTableAccess('1', 'bad')).resolves.toBe(false);
    expect(getTableToken('1')).toBeNull();
  });
  it('re-exchanges once when the token is rejected and the link still has ?k=', async () => {
    // 403 giữa chừng + URL còn ?k= -> đổi lại token rồi gửi lại 1 lần
    sessionStorage.setItem('abc_table_session_7', JSON.stringify({ token: 'stale', exp: Date.now() + 60000 }));
    window.history.pushState({}, '', '/table/7?k=abc');
    const f = vi.fn()
      .mockResolvedValueOnce(json({ detail: 'no' }, 403))
      .mockResolvedValueOnce(json({ token: 'fresh', expires_in: 21600 }))
      .mockResolvedValueOnce(json({ ok: 1 }));
    vi.stubGlobal('fetch', f);
    await expect(api.get('/orders/1/')).resolves.toEqual({ ok: 1 });
    expect(f.mock.calls[2][1].headers.get('X-Table-Token')).toBe('fresh');
  });
  it('keeps k in sessionStorage and silently renews an expired token on a new tab/day (no ?k= in URL)', async () => {
    // Quét lại cùng QR sau 6h: phiên hết hạn, URL không còn k -> tự đổi k đã lưu lấy token mới, không báo lỗi
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ token: 'T1', expires_in: 21600 })));
    await startTableSession('9', 'forever');
    expect(sessionStorage.getItem('abc_table_key_9')).toBe('forever');
    sessionStorage.setItem('abc_table_session_9', JSON.stringify({ token: 'old', exp: Date.now() - 1 }));
    const f = vi.fn()
      .mockResolvedValueOnce(json({ token: 'fresh9', expires_in: 21600 }))
      .mockResolvedValueOnce(json({ ok: 1 }));
    vi.stubGlobal('fetch', f);
    window.history.pushState({}, '', '/table/9');
    await expect(api.get('/orders/1/')).resolves.toEqual({ ok: 1 });
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ table_id: 9, k: 'forever' });
    expect(f.mock.calls[1][1].headers.get('X-Table-Token')).toBe('fresh9');
    // ensureTableAccess không k cũng gia hạn được khi token hết hạn
    sessionStorage.setItem('abc_table_session_9', JSON.stringify({ token: 'old', exp: Date.now() - 1 }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ token: 'again', expires_in: 21600 })));
    await expect(ensureTableAccess('9', null)).resolves.toBe(true);
    expect(getTableToken('9')).toBe('again');
  });
  it('renews from the stored k when the server rejects the token mid-session (no ?k= in URL)', async () => {
    sessionStorage.setItem('abc_table_session_5', JSON.stringify({ token: 'stale', exp: Date.now() + 60000 }));
    sessionStorage.setItem('abc_table_key_5', 'k5');
    window.history.pushState({}, '', '/menu?table=5');
    const f = vi.fn()
      .mockResolvedValueOnce(json({ detail: 'no' }, 403))
      .mockResolvedValueOnce(json({ token: 'fresh5', expires_in: 21600 }))
      .mockResolvedValueOnce(json({ ok: 2 }));
    vi.stubGlobal('fetch', f);
    await expect(api.get('/orders/1/')).resolves.toEqual({ ok: 2 });
    expect(f.mock.calls[2][1].headers.get('X-Table-Token')).toBe('fresh5');
  });
  it('without a stored k and a dead token, the 403 message is surfaced (scan the QR again)', async () => {
    sessionStorage.setItem('abc_table_session_6', JSON.stringify({ token: 'stale', exp: Date.now() + 60000 }));
    window.history.pushState({}, '', '/table/6');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Vui lòng quét lại mã QR trên bàn.' }, 403)));
    await expect(api.get('/orders/1/')).rejects.toThrow(/quét lại/);
  });
  it('socket for a table group uses the table token, staff groups use JWT', () => {
    // WS-02: ?token= là token phiên bàn cho table_<id>
    const sockets = [];
    vi.stubGlobal('WebSocket', class { constructor(url) { this.url = url; this.close = vi.fn(); sockets.push(this); } });
    sessionStorage.setItem('abc_table_session_4', JSON.stringify({ token: 'T4', exp: Date.now() + 60000 }));
    setTokens({ access: 'JWT' });
    const stop1 = connectSocket('table_4'); const stop2 = connectSocket('staff_orders');
    expect(sockets[0].url).toBe('ws://127.0.0.1:8000/ws/table_4/?token=T4');
    expect(sockets[1].url).toBe('ws://127.0.0.1:8000/ws/staff_orders/?token=JWT');
    stop1(); stop2(); vi.unstubAllGlobals();
  });
});
