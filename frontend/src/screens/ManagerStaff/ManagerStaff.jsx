import { useCallback, useEffect, useState } from 'react';
import { api, getUser } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const ROLES = { QL: 'Quản lý', PV: 'Nhân viên phục vụ', BEP: 'Bộ phận bếp', AD: 'Quản trị viên' };
const fmt = d => d ? new Date(d).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : 'Chưa đăng nhập';
const EMPTY = { id: null, username: '', first_name: '', email: '', role: 'PV', is_active: true, password: '' };

export default function ManagerStaff() {
  const me = getUser();
  const [users, setUsers] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState({ type: '', text: '' });

  const load = useCallback(async () => {
    try { const d = await api.get('/users/'); setUsers(d.results || d); } catch (e) { setMsg({ type: 'error', text: e.message }); }
    setLoaded(true);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  async function save(e) {
    e.preventDefault();
    const body = { first_name: form.first_name, email: form.email, role: form.role, is_active: form.is_active };
    if (form.password) body.password = form.password;
    try {
      if (form.id) await api.patch(`/users/${form.id}/`, body); else await api.post('/users/', { ...body, username: form.username.trim() });
      setForm(null); setMsg({ type: 'success', text: 'Đã lưu tài khoản.' }); await load();
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }
  async function toggle(u) {
    try { await api.patch(`/users/${u.id}/`, { is_active: !u.is_active }); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  return <div className={ui.panel}>
    <div className={ui.head}><p className={ui.lead}>Tạo tài khoản, phân vai trò và khoá khi nghỉ việc (không xoá để giữ lịch sử đơn).</p>
      <button className="btn btn-primary" onClick={() => setForm({ ...EMPTY })}><MaterialIcon name="add" size={18} />Thêm tài khoản</button></div>
    {msg.text && <div className={`alert ${msg.type === 'error' ? 'alert-danger' : 'alert-ok'}`} role="status">{msg.text}</div>}
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Tên đăng nhập</th><th>Họ tên</th><th>Email</th><th>Vai trò</th><th>Đăng nhập gần nhất</th><th>Trạng thái</th><th /></tr></thead>
      <tbody>{users.map(u => <tr key={u.id}>
        <td><b>{u.username}</b>{u.id === me?.id && <span className={ui.sub}> (bạn)</span>}</td><td>{u.first_name || '—'}</td><td>{u.email || '—'}</td>
        <td><span className="badge badge-neutral">{ROLES[u.role] || u.role}</span></td><td>{fmt(u.last_login)}</td>
        <td><span className={`badge ${u.is_active ? 'badge-ok' : 'badge-neutral'}`}>{u.is_active ? 'Hoạt động' : 'Đã khoá'}</span></td>
        <td><div className={ui.rowActions}><button className="btn btn-secondary btn-sm" onClick={() => setForm({ ...EMPTY, ...u, first_name: u.first_name || '', email: u.email || '', password: '' })}>Sửa</button>
          {u.id !== me?.id && <button className="btn btn-ghost btn-sm" onClick={() => toggle(u)}>{u.is_active ? 'Khoá' : 'Mở khoá'}</button>}</div></td>
      </tr>)}</tbody>
    </table>{!loaded ? <SkeletonRows /> : !users.length && <div className="empty"><MaterialIcon name="manage_accounts" size={32} className="empty-icon" /><p>Chưa có tài khoản nào.</p></div>}</div>

    {form && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setForm(null)}><form className="modal" onSubmit={save}>
      <div className="modal-head"><h3 className="modal-title">{form.id ? `Sửa ${form.username}` : 'Thêm tài khoản'}</h3><button type="button" className="modal-close" aria-label="Đóng" onClick={() => setForm(null)}><MaterialIcon name="close" size={20} /></button></div>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Tên đăng nhập</span><input className="input" required disabled={!!form.id} value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
        <label className="field"><span className="field-label">Họ tên</span><input className="input" value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} /></label>
        <label className="field"><span className="field-label">Email</span><input className="input" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>
        <label className="field"><span className="field-label">Vai trò</span><select className="select" value={form.role} disabled={form.id === me?.id} onChange={e => setForm({ ...form, role: e.target.value })}>{Object.entries(ROLES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field"><span className="field-label">{form.id ? 'Mật khẩu mới (để trống = giữ nguyên)' : 'Mật khẩu'}</span><input className="input" type="password" autoComplete="new-password" required={!form.id} minLength={8} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
      </div>
      <div className="modal-foot"><button type="button" className="btn btn-secondary" onClick={() => setForm(null)}>Huỷ</button><button className="btn btn-primary">Lưu</button></div>
    </form></div>}
  </div>;
}
