import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManagerSettings from './ManagerSettings';
import App from '../../App';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
const CONFIG = { cash_enabled: true, bank_transfer_enabled: true, vnpay_enabled: true, bank_bin: '', bank_name: '', bank_account_no: '',
  bank_account_name: '', staff_call_cooldown_minutes: 2, invoice_note: '', updated_at: null };

describe('ManagerSettings', () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => vi.unstubAllGlobals());

  it('loads config, shows read-only gateway status and warns when bank not configured', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ config: CONFIG, gateway: { mode: 'vnpay', tmn_code: 'CA****JV', has_hash_secret: true } })));
    render(<ManagerSettings />);
    expect(await screen.findByText('CA****JV')).toBeInTheDocument();
    expect(screen.getByText('Đã cấu hình')).toBeInTheDocument();
    expect(screen.getByText(/Chưa cấu hình tài khoản/)).toBeInTheDocument();
  });

  it('saves with PATCH and shows success', async () => {
    const f = vi.fn(async (url, opts = {}) => opts.method === 'PATCH'
      ? json({ config: { ...CONFIG, cash_enabled: false }, gateway: { mode: 'mock', tmn_code: '', has_hash_secret: false } })
      : json({ config: CONFIG, gateway: { mode: 'mock', tmn_code: '', has_hash_secret: false } }));
    vi.stubGlobal('fetch', f);
    render(<ManagerSettings />);
    await userEvent.click(await screen.findByLabelText(/Tiền mặt/));
    await userEvent.click(screen.getByRole('button', { name: /Lưu cấu hình/ }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Đã lưu cấu hình.'));
    const patch = f.mock.calls.find(c => c[1]?.method === 'PATCH');
    expect(JSON.parse(patch[1].body).cash_enabled).toBe(false);
  });

  it('shows the backend error on failure', async () => {
    const f = vi.fn(async (url, opts = {}) => opts.method === 'PATCH' ? json({ detail: 'Mã BIN ngân hàng gồm đúng 6 chữ số.' }, 400)
      : json({ config: CONFIG, gateway: { mode: 'mock', tmn_code: '', has_hash_secret: false } }));
    vi.stubGlobal('fetch', f);
    render(<ManagerSettings />);
    await userEvent.click(await screen.findByRole('button', { name: /Lưu cấu hình/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('6 chữ số');
  });
});

describe('route /manager/settings', () => {
  afterEach(() => { vi.unstubAllGlobals(); window.history.pushState({}, '', '/'); });
  it('redirects non-admin away from settings', async () => {
    localStorage.clear();
    const keys = Object.keys(localStorage);
    expect(keys.length).toBe(0);
    window.history.pushState({}, '', '/manager/settings');
    vi.stubGlobal('fetch', vi.fn(async () => json({})));
    vi.stubGlobal('WebSocket', class { constructor() { this.close = vi.fn(); } });
    render(<App />);
    // chưa đăng nhập → /login (không bao giờ hiện màn cấu hình)
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(screen.queryByText('Cấu hình hệ thống')).not.toBeInTheDocument();
  });
});
