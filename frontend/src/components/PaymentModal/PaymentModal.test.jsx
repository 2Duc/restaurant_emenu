import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentModal from './PaymentModal';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
const BANK_PAYMENT = {
  id: 7, method: 'bank_transfer', status: 'pending', amount: '170000', qr_image: 'data:image/png;base64,AAA',
  bank_info: { bank_name: 'Vietcombank', account_no: '0011001234567', account_name: 'ABC RESTAURANT', content: 'DON12', amount: 170000 },
};

function mockApi(methods, extra = {}) {
  const f = vi.fn(async (url, opts = {}) => {
    const u = String(url);
    if (u.endsWith('/settings/')) return json({ methods, bank: null });
    if (u.includes('/orders/12/')) return json({ id: 12, total_amount: '170000' });
    if (u.endsWith('/payments/create/')) return extra.create ? extra.create(JSON.parse(opts.body)) : json(BANK_PAYMENT, 201);
    return json({});
  });
  vi.stubGlobal('fetch', f);
  return f;
}

describe('PaymentModal: phương thức theo cấu hình', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
  afterEach(() => vi.unstubAllGlobals());

  it('hides disabled methods and shows bank transfer only when enabled', async () => {
    mockApi({ cash: false, bank_transfer: true, vnpay: false });
    render(<PaymentModal orderId={12} onClose={() => {}} />);
    expect(await screen.findByText('Chuyển khoản ngân hàng')).toBeInTheDocument();
    expect(screen.queryByText('Tiền mặt')).not.toBeInTheDocument();
    expect(screen.queryByText('Chuyển khoản')).not.toBeInTheDocument();
  });

  it('shows the 2 original options and no bank option when bank is off', async () => {
    mockApi({ cash: true, bank_transfer: false, vnpay: true });
    render(<PaymentModal orderId={12} onClose={() => {}} />);
    expect(await screen.findByText('Tiền mặt')).toBeInTheDocument();
    expect(screen.getByText('Chuyển khoản')).toBeInTheDocument();
    expect(screen.queryByText('Chuyển khoản ngân hàng')).not.toBeInTheDocument();
  });

  it('bank transfer: posts method, shows account info, QR and waiting text', async () => {
    const f = mockApi({ cash: true, bank_transfer: true, vnpay: true });
    render(<PaymentModal orderId={12} onClose={() => {}} />);
    await userEvent.click(await screen.findByText('Chuyển khoản ngân hàng'));
    expect(await screen.findByText('0011001234567')).toBeInTheDocument();
    expect(screen.getByText('ABC RESTAURANT')).toBeInTheDocument();
    expect(screen.getByText('DON12')).toBeInTheDocument();
    expect(screen.getByAltText('Mã VietQR chuyển khoản')).toHaveAttribute('src', BANK_PAYMENT.qr_image);
    expect(screen.getByText(/Đang chờ nhân viên xác nhận/)).toBeInTheDocument();
    const call = f.mock.calls.find(c => String(c[0]).endsWith('/payments/create/'));
    expect(JSON.parse(call[1].body)).toEqual({ order_id: 12, method: 'bank_transfer' });
  });

  it('shows the backend error when the method is rejected (400)', async () => {
    mockApi({ cash: true, bank_transfer: true, vnpay: true }, { create: () => json({ detail: 'Phương thức thanh toán này hiện không khả dụng.' }, 400) });
    render(<PaymentModal orderId={12} onClose={() => {}} />);
    await userEvent.click(await screen.findByText('Chuyển khoản ngân hàng'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('không khả dụng'));
  });
});
