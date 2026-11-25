import { useState } from 'react';
import { api } from '../../services/api';
import styles from './styles.module.css';

/** BR-15: yêu cầu nhập lại mật khẩu trước khi quay về chế độ Quản lý. */
export default function ReauthModal({ title = 'Xác nhận lại mật khẩu', onSuccess, onClose }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api.post('/auth/reauth/', { password }); await onSuccess(); }
    catch (err) { setError(err.message || 'Không xác nhận được mật khẩu.'); setBusy(false); }
  }

  return <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
    <form className="modal modal-sm" onSubmit={submit}>
      <h2 className="modal-title">{title}</h2>
      <p className={styles.text}>Vì lý do bảo mật, hãy nhập lại mật khẩu để quay về chế độ Quản lý.</p>
      <input className="input" type="password" autoFocus autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Mật khẩu của bạn" aria-label="Mật khẩu" />
      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      <div className="modal-foot">
        <button type="button" className="btn btn-ghost" onClick={onClose}>Huỷ</button>
        <button className="btn btn-primary" aria-busy={busy} disabled={busy}>{busy ? 'Đang xác nhận…' : 'Xác nhận'}</button>
      </div>
    </form>
  </div>;
}
