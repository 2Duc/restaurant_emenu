import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog, PromptDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  it('renders message and default labels', () => {
    // Hiển thị nội dung và nhãn mặc định
    render(<ConfirmDialog message="Xoá bàn?" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText('Xoá bàn?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Xác nhận' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Huỷ bỏ' })).toBeInTheDocument();
  });
  it('calls onConfirm when confirm button is clicked', async () => {
    // Bấm xác nhận -> onConfirm, không gọi onCancel
    const onConfirm = vi.fn(); const onCancel = vi.fn();
    render(<ConfirmDialog message="m" onConfirm={onConfirm} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole('button', { name: 'Xác nhận' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });
  it('calls onCancel when cancel button is clicked', async () => {
    // Bấm Huỷ -> onCancel
    const onCancel = vi.fn();
    render(<ConfirmDialog message="m" onConfirm={() => {}} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole('button', { name: 'Huỷ bỏ' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
  it('calls onCancel on Escape key', () => {
    // Nhấn Esc -> huỷ
    const onCancel = vi.fn();
    render(<ConfirmDialog message="m" onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
  it('focuses the confirm button so Enter confirms', async () => {
    // Nút xác nhận autoFocus; Enter kích hoạt xác nhận
    const onConfirm = vi.fn();
    render(<ConfirmDialog message="m" confirmLabel="Xoá" danger onConfirm={onConfirm} onCancel={() => {}} />);
    const btn = screen.getByRole('button', { name: 'Xoá' });
    expect(btn).toHaveFocus();
    expect(btn).toHaveClass('btn-danger');
    await userEvent.keyboard('{Enter}');
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
  it('cancels when clicking the backdrop but not the dialog body', async () => {
    // Bấm nền mờ -> huỷ; bấm trong hộp thoại -> không huỷ
    const onCancel = vi.fn();
    const { container } = render(<ConfirmDialog message="m" onConfirm={() => {}} onCancel={onCancel} />);
    await userEvent.click(screen.getByText('m'));
    expect(onCancel).not.toHaveBeenCalled();
    await userEvent.click(container.querySelector('.modal-backdrop'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('PromptDialog', () => {
  it('submits entered values', async () => {
    // Nhập giá trị rồi Lưu -> onSubmit nhận object giá trị
    const onSubmit = vi.fn();
    render(<PromptDialog title="Sửa" fields={[{ name: 'capacity', label: 'Sức chứa', type: 'number', value: 4 }]} onSubmit={onSubmit} onCancel={() => {}} />);
    const input = screen.getByLabelText('Sức chứa');
    await userEvent.clear(input);
    await userEvent.type(input, '8');
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }));
    expect(onSubmit).toHaveBeenCalledWith({ capacity: '8' });
  });
});
