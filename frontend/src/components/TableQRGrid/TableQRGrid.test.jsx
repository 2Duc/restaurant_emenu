import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../services/api', () => ({ api: { get: vi.fn() }, saveFile: vi.fn().mockResolvedValue() }));
import { api, saveFile } from '../../services/api';
import TableQRGrid from './TableQRGrid';

const codes = [1, 2, 3].map(i => ({ id: i, table_id: i, area: 'A', url: `http://x/table/${i}?k=k${i}`, qr_image: 'data:image/png;base64,AA', base_url: 'http://x', default_base_url: 'http://x' }));

describe('TableQRGrid (màn In QR)', () => {
  beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(codes); });

  it('renders a sticker card per table with brand, table number and scan hint', async () => {
    render(<TableQRGrid />);
    expect(await screen.findByText('Bàn 3')).toBeTruthy();
    expect(screen.getAllByText('ABC Restaurant')).toHaveLength(3);
    expect(screen.getAllByText('Quét để xem thực đơn và gọi món')).toHaveLength(3);
    expect(screen.getByText('Tất cả 3 bàn')).toBeTruthy();
  });

  it('selects tables and downloads only the selected ones as PDF / zip; per-table PNG uses card=1', async () => {
    render(<TableQRGrid />);
    await screen.findByText('Bàn 1');
    fireEvent.click(screen.getByLabelText('Chọn bàn 2 để in'));
    fireEvent.click(screen.getByLabelText('Chọn bàn 3 để in'));
    expect(screen.getByText('Đã chọn 2/3 bàn')).toBeTruthy();
    fireEvent.click(screen.getByText('Tải PDF A4'));
    await waitFor(() => expect(saveFile).toHaveBeenCalledTimes(1));
    expect(saveFile.mock.calls[0][0]).toMatch(/^\/tables\/qr-pdf\/\?.*ids=2,3/);
    fireEvent.click(screen.getByText('Tải tất cả (zip)'));
    await waitFor(() => expect(saveFile).toHaveBeenCalledTimes(2));
    expect(saveFile.mock.calls[1][0]).toMatch(/qr-zip\/\?.*ids=2,3/);
    fireEvent.click(screen.getAllByText('Tải PNG')[0]);
    await waitFor(() => expect(saveFile).toHaveBeenCalledTimes(3));
    expect(saveFile.mock.calls[2][0]).toMatch(/^\/tables\/1\/qr-png\/\?card=1/);
  });

  it('without selection downloads all (no ids) and window.print prints', async () => {
    window.print = vi.fn();
    render(<TableQRGrid />);
    await screen.findByText('Bàn 1');
    fireEvent.click(screen.getByText('Tải tất cả (zip)'));
    await waitFor(() => expect(saveFile).toHaveBeenCalled());
    expect(saveFile.mock.calls[0][0]).not.toMatch(/ids=/);
    fireEvent.click(screen.getByText('In tất cả'));
    expect(window.print).toHaveBeenCalled();
  });

  it('warns when the chosen website address differs from the server configured one', async () => {
    api.get.mockResolvedValue(codes.map(c => ({ ...c, default_base_url: 'https://abc.example.com' })));
    render(<TableQRGrid />);
    await screen.findByText('Bàn 1');
    expect(screen.getByRole('alert').textContent).toMatch(/khác địa chỉ cấu hình/);
  });

  it('shows a single table when tableId is given', async () => {
    render(<TableQRGrid tableId={2} />);
    expect(await screen.findByText('Bàn 2')).toBeTruthy();
    expect(screen.queryByText('Bàn 1')).toBeNull();
  });
});
