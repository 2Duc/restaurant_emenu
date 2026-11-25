import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { useConfirm } from './useConfirm';

function Host({ onResult }) {
  const [confirm, dialog] = useConfirm();
  return <><button onClick={async () => onResult(await confirm('Chắc chứ?', { confirmLabel: 'Đồng ý' }))}>mở</button>{dialog}</>;
}

describe('useConfirm', () => {
  it('resolves true when confirmed and closes the dialog', async () => {
    // Xác nhận -> promise resolve true, hộp thoại đóng
    const results = [];
    render(<Host onResult={r => results.push(r)} />);
    await userEvent.click(screen.getByText('mở'));
    expect(screen.getByText('Chắc chứ?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Đồng ý' }));
    await act(async () => {});
    expect(results).toEqual([true]);
    expect(screen.queryByText('Chắc chứ?')).toBeNull();
  });
  it('resolves false when cancelled', async () => {
    // Huỷ -> resolve false
    const results = [];
    render(<Host onResult={r => results.push(r)} />);
    await userEvent.click(screen.getByText('mở'));
    await userEvent.click(screen.getByRole('button', { name: 'Huỷ bỏ' }));
    await act(async () => {});
    expect(results).toEqual([false]);
  });
});
