const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '');
const TOKEN_KEY = 'abc_access_token';
const REFRESH_KEY = 'abc_refresh_token';
const USER_KEY = 'abc_user';

// Vai trò: AD quản trị, QL quản lý, PV phục vụ, BEP bếp.
export const HOME_BY_ROLE = { AD: '/manager', QL: '/manager', PV: '/waiter', BEP: '/chef' };
export function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; } }
export function setUser(user) { if (user) localStorage.setItem(USER_KEY, JSON.stringify(user)); }
// Superuser của Django có toàn quyền ở backend, nên giao diện cũng coi như quản trị viên (AD).
export function getRole() { const u = getUser(); return u?.is_superuser ? 'AD' : (u?.role || null); }

export function getAccessToken() { return localStorage.getItem(TOKEN_KEY); }
export function setTokens(data) {
  if (data?.access) localStorage.setItem(TOKEN_KEY, data.access);
  if (data?.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
}
export function clearTokens() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY); localStorage.removeItem(USER_KEY); }

// BR-02 / AUTH-05: khách chỉ thao tác trong bàn của mình. Link QR là /table/<id>?k=<mã>; mã k được đổi lấy
// token phiên bàn (ký, hạn ~6 giờ) lưu trong sessionStorage theo bàn và gửi kèm mọi yêu cầu qua header X-Table-Token.
// X-Table-Id vẫn được gửi nhưng backend chỉ dùng để log, không dùng để phân quyền.
const TABLE_SESSION_PREFIX = 'abc_table_session_';
function readTableSession(tableId) {
  try {
    const s = JSON.parse(sessionStorage.getItem(TABLE_SESSION_PREFIX + tableId) || 'null');
    return s?.token && s.exp > Date.now() ? s : null;
  } catch { return null; }
}
export function getTableToken(tableId) { return tableId ? readTableSession(tableId)?.token || null : null; }
export function clearTableSession(tableId) { try { sessionStorage.removeItem(TABLE_SESSION_PREFIX + tableId); sessionStorage.removeItem('abc_table_key_' + tableId); } catch { /* storage bị chặn */ } }
// Mã k của link QR cũng được giữ trong sessionStorage để khi token phiên hết hạn (sau 6 giờ) hoặc tải lại trang
// không còn ?k= trên URL thì vẫn tự đổi lấy token mới, không hiện lỗi. QR đã in dùng lại được vô hạn lần.
const TABLE_KEY_PREFIX = 'abc_table_key_';
function readTableKey(tableId) {
  try { return sessionStorage.getItem(TABLE_KEY_PREFIX + tableId) || null; } catch { return null; }
}
const renewing = new Map();
const renewFailedAt = new Map();   // tránh gọi dồn dập (throttle 30/phút) khi k đã bị đổi/không còn hiệu lực
export async function startTableSession(tableId, key) {
  const data = await request('/tables/session/', { method: 'POST', body: JSON.stringify({ table_id: Number(tableId), k: key }), noTableRetry: true });
  try {
    sessionStorage.setItem(TABLE_SESSION_PREFIX + tableId, JSON.stringify({ token: data.token, exp: Date.now() + Math.max(60, (data.expires_in || 21600) - 120) * 1000 }));
    sessionStorage.setItem(TABLE_KEY_PREFIX + tableId, key);
  } catch { /* storage bị chặn */ }
  return data.token;
}
// Tự gia hạn phiên bàn bằng k (trên URL hoặc đã lưu). Trả về token mới, hoặc null nếu không có k / k không còn hiệu lực.
export function renewTableSession(tableId, urlKey = null) {
  const key = urlKey || readTableKey(tableId);
  if (!tableId || !key) return Promise.resolve(null);
  const id = String(tableId);
  if (!urlKey && Date.now() - (renewFailedAt.get(id) || 0) < 30000) return Promise.resolve(null);
  if (!renewing.has(id)) {
    renewing.set(id, startTableSession(id, key).catch(() => { renewFailedAt.set(id, Date.now()); return null; }).finally(() => renewing.delete(id)));
  }
  return renewing.get(id);
}
// Mở bàn từ link QR: có k thì đổi lấy token mới; không có k thì dùng token đã lưu, hết hạn thì gia hạn bằng k đã lưu.
// Trả về true nếu khách có phiên bàn hợp lệ.
export async function ensureTableAccess(tableId, key) {
  if (key) { try { await startTableSession(tableId, key); return true; } catch { clearTableSession(tableId); return false; } }
  if (getTableToken(tableId)) return true;
  return Boolean(await renewTableSession(tableId));
}

function currentTableId() {
  const fromPath = window.location.pathname.match(/^\/table\/(\d+)/);
  if (fromPath) return fromPath[1];
  const legacy = new URLSearchParams(window.location.search).get('table');
  // /menu?table=<id> (link cũ) và /payment-result?table=<id> (VNPay quay về) đều mang theo bàn của khách.
  return ['/menu', '/payment-result'].includes(window.location.pathname) && /^\d+$/.test(legacy || '') ? legacy : null;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const tableId = currentTableId();
  const urlKey = new URLSearchParams(window.location.search).get('k');
  if (tableId && !options.noTableRetry && !getTableToken(tableId)) await renewTableSession(tableId, urlKey);
  if (tableId) {
    headers.set('X-Table-Id', tableId);
    const tableToken = getTableToken(tableId);
    if (tableToken) headers.set('X-Table-Token', tableToken);
  }
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (!(options.body instanceof FormData) && options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const { noTableRetry, ...fetchOptions } = options;
  let response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, { ...fetchOptions, headers });
  // Token phiên bàn hết hạn giữa chừng mà link vẫn còn ?k= -> đổi lại token rồi gửi lại 1 lần.
  if (response.status === 403 && tableId && !noTableRetry && headers.has('X-Table-Token')) {
    const renewed = await renewTableSession(tableId, urlKey);
    if (renewed) {
      headers.set('X-Table-Token', renewed);
      response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, { ...fetchOptions, headers });
    }
  }
  if (response.status === 401 && localStorage.getItem(REFRESH_KEY)) {
    const refresh = localStorage.getItem(REFRESH_KEY);
    const renewed = await fetch(`${API_BASE}/auth/refresh/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }) });
    if (renewed.ok) {
      const tokens = await renewed.json(); setTokens(tokens);
      headers.set('Authorization', `Bearer ${tokens.access}`);
      response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, { ...fetchOptions, headers });
    } else clearTokens();
  }
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
  if (!response.ok) {
    const message = payload?.detail || payload?.message || (typeof payload === 'string' ? payload : 'Có lỗi xảy ra khi gọi API.');
    throw new Error(message);
  }
  return payload;
}

// Tải file nhị phân (PNG/PDF/zip) bằng yêu cầu có JWT; trả về { blob, filename }.
export async function downloadFile(path) {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    let detail = 'Không tải được tệp.';
    try { detail = (await response.json()).detail || detail; } catch { /* không phải JSON */ }
    throw new Error(detail);
  }
  const match = /filename="?([^";]+)"?/.exec(response.headers.get('Content-Disposition') || '');
  return { blob: await response.blob(), filename: match ? match[1] : 'qr' };
}
export async function saveFile(path, fallbackName) {
  const { blob, filename } = await downloadFile(path);
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href; a.download = filename || fallbackName; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export const api = {
  get: (path) => request(path),
  post: (path, data) => request(path, { method: 'POST', body: JSON.stringify(data) }),
  patch: (path, data) => request(path, { method: 'PATCH', body: JSON.stringify(data) }),
  put: (path, data) => request(path, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData }),
  patchForm: (path, formData) => request(path, { method: 'PATCH', body: formData }),
};

export async function login(username, password) {
  const result = await api.post('/auth/login/', { username, password });
  setTokens(result); setUser(result.user); return result;
}
export function logout() { clearTokens(); }
export function openSocket(group) {
  const wsBase = (import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000').replace(/\/$/, '');
  // WS-02: kênh bàn dùng token phiên bàn (khách); kênh nhân viên dùng JWT. Nhân viên mở kênh bàn vẫn dùng JWT.
  const tableMatch = /^table_(\d+)$/.exec(group);
  const token = (tableMatch && getTableToken(tableMatch[1])) || getAccessToken();
  return new WebSocket(`${wsBase}/ws/${group}/${token ? `?token=${encodeURIComponent(token)}` : ''}`);
}
const NBSP = String.fromCharCode(160);
export const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')}${NBSP}₫`;

// WebSocket tự nối lại (1s → 2s → 5s → 10s). Trả về hàm đóng; handlers: onMessage, onOpen, onClose.
export function connectSocket(group, { onMessage, onOpen, onClose } = {}) {
  const delays = [1000, 2000, 5000, 10000];
  let socket; let timer; let attempt = 0; let stopped = false;
  const connect = () => {
    if (stopped) return;
    try { socket = openSocket(group); } catch { timer = setTimeout(connect, delays[Math.min(attempt++, 3)]); return; }
    socket.onopen = () => { attempt = 0; onOpen?.(); };
    socket.onmessage = (e) => onMessage?.(e);
    socket.onclose = () => { onClose?.(); if (!stopped) timer = setTimeout(connect, delays[Math.min(attempt++, 3)]); };
  };
  connect();
  return () => { stopped = true; clearTimeout(timer); if (socket) { socket.onclose = null; socket.onopen = null; socket.onmessage = null; socket.close(); } };
}
