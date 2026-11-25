import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const pad = n => String(n).padStart(2, '0');
const toLocalInput = d => { const x = new Date(d); return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}T${pad(x.getHours())}:${pad(x.getMinutes())}`; };
const fresh = () => { const now = new Date(); const end = new Date(now.getTime() + 30 * 864e5); return { id: null, code: '', discount_type: 'percent', value: '10', menu_item: '', start_date: toLocalInput(now), end_date: toLocalInput(end), is_active: true }; };
const fmt = d => new Date(d).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });

function state(p) {
  const now = Date.now();
  if (!p.is_active) return ['Đã tắt', 'badge-neutral'];
  if (new Date(p.end_date) < now) return ['Hết hạn', 'badge-danger'];
  if (new Date(p.start_date) > now) return ['Chưa bắt đầu', 'badge-warn'];
  return ['Đang hiệu lực', 'badge-ok'];
}

export default function ManagerPromotions() {
  const [confirm, confirmDialog] = useConfirm();
  const [list, setList] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [dishes, setDishes] = useState([]);
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState({ type: '', text: '' });

  const load = useCallback(async () => {
    try { const [d, m] = await Promise.all([api.get('/promotions/'), api.get('/menu-items/?ordering=name')]); setList(d.results || d); setDishes(m.results || m); } catch (e) { setMsg({ type: 'error', text: e.message }); }
    setLoaded(true);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  async function save(e) {
    e.preventDefault();
    const body = { code: form.code, discount_type: form.discount_type, value: Number(form.value), is_active: form.is_active, menu_item: form.menu_item ? Number(form.menu_item) : null,
      start_date: new Date(form.start_date).toISOString(), end_date: new Date(form.end_date).toISOString() };
    try {
      if (form.id) await api.patch(`/promotions/${form.id}/`, body); else await api.post('/promotions/', body);
      setForm(null); setMsg({ type: 'success', text: 'Đã lưu mã khuyến mãi.' }); await load();
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }
  async function toggle(p) { try { await api.patch(`/promotions/${p.id}/`, { is_active: !p.is_active }); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); } }
  async function remove(p) {
    if (!await confirm(`Xoá mã ${p.code}?`, { danger: true, confirmLabel: 'Xoá' })) return;
    try { await api.delete(`/promotions/${p.id}/`); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  return <div className={ui.panel}>
    {confirmDialog}
    <div className={ui.head}><p className={ui.lead}>Khách nhập mã ở giỏ hàng; giảm theo phần trăm hoặc số tiền cố định.</p>
      <button className="btn btn-primary" onClick={() => setForm(fresh())}><MaterialIcon name="add" size={18} />Tạo mã mới</button></div>
    {msg.text && <div className={`alert ${msg.type === 'error' ? 'alert-danger' : 'alert-ok'}`} role="status">{msg.text}</div>}
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Mã</th><th>Áp dụng cho</th><th className="num">Giảm</th><th>Hiệu lực</th><th>Trạng thái</th><th /></tr></thead>
      <tbody>{list.map(p => { const [label, cls] = state(p); return <tr key={p.id}>
        <td><b className={ui.code}>{p.code}</b></td>
        <td>{p.menu_item_name ? `Món: ${p.menu_item_name}` : 'Cả đơn'}</td>
        <td className="num">{p.discount_type === 'percent' ? `${Number(p.value)}%` : `${Number(p.value).toLocaleString('vi-VN')}đ`}</td>
        <td>{fmt(p.start_date)} → {fmt(p.end_date)}</td>
        <td><span className={`badge ${cls}`}>{label}</span></td>
        <td><div className={ui.rowActions}>
          <button className="btn btn-secondary btn-sm" onClick={() => toggle(p)}>{p.is_active ? 'Tắt' : 'Bật'}</button>
          <button className="btn btn-secondary btn-sm" onClick={() => setForm({ ...p, menu_item: p.menu_item ?? '', value: String(Number(p.value)), start_date: toLocalInput(p.start_date), end_date: toLocalInput(p.end_date) })}>Sửa</button>
          <button className="btn btn-ghost btn-sm" onClick={() => remove(p)}>Xoá</button></div></td>
      </tr>; })}</tbody>
    </table>{!loaded ? <SkeletonRows /> : !list.length && <div className="empty"><MaterialIcon name="confirmation_number" size={32} className="empty-icon" /><p>Chưa có mã khuyến mãi nào. Bấm “Tạo mã mới” để bắt đầu.</p></div>}</div>

    {form && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setForm(null)}><form className="modal" onSubmit={save}>
      <div className="modal-head"><h3 className="modal-title">{form.id ? 'Sửa khuyến mãi' : 'Tạo khuyến mãi'}</h3><button type="button" className="modal-close" aria-label="Đóng" onClick={() => setForm(null)}><MaterialIcon name="close" size={20} /></button></div>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Mã voucher</span><input className="input" required value={form.code} onChange={e => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="VD: ABC10" /></label>
        <label className="field"><span className="field-label">Loại giảm</span><select className="select" value={form.discount_type} onChange={e => setForm({ ...form, discount_type: e.target.value })}><option value="percent">Phần trăm (%)</option><option value="fixed">Số tiền cố định (VND)</option></select></label>
        <label className="field"><span className="field-label">Giá trị</span><input className="input" required type="number" min="1" max={form.discount_type === 'percent' ? 100 : undefined} value={form.value} onChange={e => setForm({ ...form, value: e.target.value })} /></label>
        <label className="field"><span className="field-label">Áp dụng cho</span><select className="select" value={form.menu_item} onChange={e => setForm({ ...form, menu_item: e.target.value })}><option value="">Cả đơn hàng</option>{dishes.map(d => <option key={d.id} value={d.id}>Chỉ món: {d.name}</option>)}</select></label>
        <label className="field"><span className="field-label">Bắt đầu</span><input className="input" required type="datetime-local" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} /></label>
        <label className="field"><span className="field-label">Kết thúc</span><input className="input" required type="datetime-local" value={form.end_date} min={form.start_date} onChange={e => setForm({ ...form, end_date: e.target.value })} /></label>
      </div>
      <label className={ui.check}><input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} /> Đang kích hoạt</label>
      <div className="modal-foot"><button type="button" className="btn btn-secondary" onClick={() => setForm(null)}>Huỷ</button><button className="btn btn-primary">Lưu</button></div>
    </form></div>}
  </div>;
}
