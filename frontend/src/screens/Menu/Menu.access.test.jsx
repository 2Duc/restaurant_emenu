import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Menu from './Menu';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });

function renderAt(url) {
  window.history.pushState({}, '', url);
  return render(<MemoryRouter initialEntries={[url]}><Routes><Route path="/table/:tableId" element={<Menu />} /></Routes></MemoryRouter>);
}

describe('Menu: truy cập bằng link QR có mã k (AUTH-05)', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear();
    vi.stubGlobal('WebSocket', class { constructor() { this.close = vi.fn(); } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('shows a friendly error and makes no data calls when k is missing and there is no session', async () => {
    const f = vi.fn().mockResolvedValue(json({}));
    vi.stubGlobal('fetch', f);
    renderAt('/table/5');
    expect(await screen.findByRole('alert')).toHaveTextContent('Không mở được bàn');
    expect(f).not.toHaveBeenCalled();
  });
  it('shows the error when k is wrong', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'bad' }, 403)));
    renderAt('/table/5?k=wrong');
    expect(await screen.findByRole('alert')).toHaveTextContent('Không mở được bàn');
    expect(sessionStorage.getItem('abc_table_session_5')).toBeNull();
  });
  it('exchanges k for a token, stores it and sends it on later calls', async () => {
    const f = vi.fn(async (url) => {
      if (String(url).endsWith('/tables/session/')) return json({ token: 'TOK5', table_id: 5, expires_in: 21600 });
      if (String(url).includes('/tables/5/current-order/')) return json({ detail: 'none' }, 404);
      if (String(url).includes('/tables/5/')) return json({ id: 5, number: '5', area: 'A', status: 'empty' });
      return json([]);
    });
    vi.stubGlobal('fetch', f);
    renderAt('/table/5?k=good');
    await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes('/tables/5/current-order/'))).toBe(true));
    expect(JSON.parse(sessionStorage.getItem('abc_table_session_5')).token).toBe('TOK5');
    const call = f.mock.calls.find(([u]) => String(u).includes('/tables/5/current-order/'));
    expect(call[1].headers.get('X-Table-Token')).toBe('TOK5');
    expect(screen.queryByText('Không mở được bàn')).toBeNull();
  });
});
