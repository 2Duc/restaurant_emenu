import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Manager from './Manager';

const json = (body) => new Response(JSON.stringify(body), { status: 200 });

describe('Manager sidebar: Cấu hình hệ thống chỉ cho AD', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('WebSocket', class { constructor() { this.close = vi.fn(); } });
    vi.stubGlobal('fetch', vi.fn(async () => json([])));
  });
  afterEach(() => vi.unstubAllGlobals());
  const as = (role) => { localStorage.setItem('abc_user', JSON.stringify({ username: 'u', role })); localStorage.setItem('abc_access_token', 't'); };

  it('hides the item for QL', () => {
    as('QL');
    render(<MemoryRouter><Manager /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /Cấu hình hệ thống/ })).not.toBeInTheDocument();
  });
  it('shows the item for AD', () => {
    as('AD');
    render(<MemoryRouter><Manager /></MemoryRouter>);
    expect(screen.getByRole('button', { name: /Cấu hình hệ thống/ })).toBeInTheDocument();
  });
  it('QL cannot open settings even via initialNav', () => {
    as('QL');
    render(<MemoryRouter><Manager initialNav="settings" /></MemoryRouter>);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Tổng quan');
  });
});
