import { useState } from 'react';
import { api } from '../../services/api';

/** Mọi vai trò tự đổi mật khẩu của mình. */
export default function ChangePasswordModal({ onClose }) {
  const [form, setForm] = useState({ old_password: '', new_password: '', confirm: '' });
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function submit(e) {
    e.preventDefault(); setError('');
    if (form.new_password !== form.confirm) { setError('Mật khẩu nhập lại không khớp.'); return; }
    setBusy(true);
    try { await api.post('/auth/change-password/', { old_password: form.old_password, new_password: form.new_password }); setDone(true); }
    catch (err) { setError(err.message || 'Không đổi được mật khẩu.'); }
    finally { setBusy(false); }
  }

  return <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
    <form className="modal modal-sm" onSubmit={submit}>
      <h2 className="modal-title">Đổi mật khẩu</h2>
      {done ? <>
        <div className="alert alert-ok" role="status">Đã đổi mật khẩu thành công.</div>
        <div className="modal-foot"><button type="button" className="btn btn-primary" onClick={onClose}>Đóng</button></div>
      </> : <>
        <input className="input" type="password" autoComplete="current-password" required value={form.old_password} onChange={e => set('old_password', e.target.value)} placeholder="Mật khẩu hiện tại" aria-label="Mật khẩu hiện tại" />
        <input className="input" type="password" autoComplete="new-password" required minLength={8} value={form.new_password} onChange={e => set('new_password', e.target.value)} placeholder="Mật khẩu mới (tối thiểu 8 ký tự)" aria-label="Mật khẩu mới" />
        <input className="input" type="password" autoComplete="new-password" required value={form.confirm} onChange={e => set('confirm', e.target.value)} placeholder="Nhập lại mật khẩu mới" aria-label="Nhập lại mật khẩu mới" />
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <div className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Huỷ</button>
          <button className="btn btn-primary" aria-busy={busy} disabled={busy}>{busy ? 'Đang lưu…' : 'Đổi mật khẩu'}</button>
        </div>
      </>}
    </form>
  </div>;
}
