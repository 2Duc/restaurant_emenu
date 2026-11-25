import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { PromptDialog } from '../../components/ConfirmDialog/ConfirmDialog';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import TableQRGrid from '../../components/TableQRGrid/TableQRGrid';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const STATUS = { empty: ['Trống', 'badge-ok'], occupied: ['Đang sử dụng', 'badge-warn'], cleaning: ['Chờ dọn', 'badge-neutral'] };

// Số bàn = id bàn (tự gán), nên chỉ cần nhập khu vực và sức chứa khi thêm bàn.
export default function ManagerTables({ refreshKey = 0 }) {
  const [tables, setTables] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState({ area: 'Khu A', capacity: 4 });
  const [msg, setMsg] = useState({ type: '', text: '' });
  const [view, setView] = useState('list');      // list | qr
  const [qrTable, setQrTable] = useState(null);   // null = QR của tất cả bàn
  const [editing, setEditing] = useState(null);   // bàn đang sửa
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(async () => {
    try { const d = await api.get('/tables/'); setTables(d.results || d); } catch (e) { setMsg({ type: 'error', text: e.message }); }
    setLoaded(true);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load, refreshKey]);

  async function add(e) {
    e.preventDefault();
    try { const t = await api.post('/tables/', { area: form.area, capacity: Number(form.capacity) }); setMsg({ type: 'success', text: `Đã thêm bàn ${t.id}.` }); await load(); }
    catch (err) { setMsg({ type: 'error', text: err.message }); }
  }
  async function setStatus(t, status) { try { await api.patch(`/tables/${t.id}/status/`, { status }); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); } }
  async function saveEdit(t, { area, cap }) {
    if (!Number(cap)) return;
    setEditing(null);
    try { await api.patch(`/tables/${t.id}/`, { area, capacity: Number(cap) }); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }
  async function remove(t) {
    if (!await confirm(`Xoá bàn ${t.id}? Các đơn của bàn này cũng bị xoá.`, { danger: true, confirmLabel: 'Xoá' })) return;
    try { await api.delete(`/tables/${t.id}/`); await load(); } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  async function rotateQr(t) {
    if (!await confirm(`Đổi mã QR bàn ${t.id}? Mã QR đã in và các phiên đang mở của bàn này sẽ ngừng hoạt động.`, { danger: true, confirmLabel: 'Đổi mã QR' })) return;
    try { await api.post(`/tables/${t.id}/rotate-qr/`, {}); setMsg({ type: 'success', text: `Đã đổi mã QR bàn ${t.id}. Hãy in lại mã QR mới ở mục "Mã QR".` }); }
    catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  return <div className={ui.panel}>
    {confirmDialog}
    {editing && <PromptDialog title={`Sửa bàn ${editing.id}`} fields={[
      { name: 'area', label: `Khu vực của bàn ${editing.id}:`, value: editing.area || '' },
      { name: 'cap', label: 'Sức chứa (số khách):', type: 'number', min: 1, max: 50, value: editing.capacity }]}
      onSubmit={v => saveEdit(editing, v)} onCancel={() => setEditing(null)} />}
    <div className={ui.head}><p className={ui.lead}>Mỗi bàn có một id, cũng là số bàn trên link QR (/table/&lt;id&gt;).</p>
      <div className="tabs" role="tablist" aria-label="Chế độ xem">
        <button role="tab" aria-selected={view === 'list'} onClick={() => setView('list')}>Danh sách bàn</button>
        <button role="tab" aria-selected={view === 'qr'} onClick={() => { setQrTable(null); setView('qr'); }}>Mã QR các bàn</button>
      </div></div>
    {msg.text && <div className={`alert ${msg.type === 'error' ? 'alert-danger' : 'alert-ok'}`} role="status">{msg.text}</div>}
    {view === 'qr' ? <div className="card"><TableQRGrid tableId={qrTable} onShowAll={() => setQrTable(null)} /></div> : <>
    <form className={`card ${ui.toolbar}`} onSubmit={add}>
      <label className="field"><span className="field-label">Khu vực</span><input className="input" value={form.area} onChange={e => setForm({ ...form, area: e.target.value })} /></label>
      <label className="field"><span className="field-label">Sức chứa</span><input className="input" type="number" min="1" max="50" value={form.capacity} onChange={e => setForm({ ...form, capacity: e.target.value })} /></label>
      <button className="btn btn-primary"><MaterialIcon name="add" size={18} />Thêm bàn</button>
    </form>
    <div className={ui.tableGrid}>{tables.map(t => { const [l, c] = STATUS[t.status] || [t.status, 'badge-neutral']; return <article key={t.id} className={`card ${ui.tableCard}`}>
      <div className={ui.tableCardTop}><h3>Bàn {t.id}</h3><span className={`badge ${c}`}>{l}</span></div>
      <p className={ui.tableCardMeta}>{t.area || 'Nhà hàng'} · {t.capacity} chỗ</p>
      <code className={ui.code}>/table/{t.id}</code>
      <select className="select" aria-label={`Trạng thái bàn ${t.id}`} value={t.status} onChange={e => setStatus(t, e.target.value)}>{Object.entries(STATUS).map(([k, [lab]]) => <option key={k} value={k}>{lab}</option>)}</select>
      <div className={ui.tableCardActions}><button className="btn btn-secondary btn-sm" onClick={() => { setQrTable(t.id); setView('qr'); }}>Mã QR</button><button className="btn btn-secondary btn-sm" onClick={() => setEditing(t)}>Sửa</button><button className="btn btn-secondary btn-sm" onClick={() => rotateQr(t)}>Đổi mã QR</button><button className="btn btn-ghost btn-sm" onClick={() => remove(t)}>Xoá</button></div>
    </article>; })}</div>
    {!loaded ? <SkeletonRows /> : !tables.length && <div className="empty card"><MaterialIcon name="table_restaurant" size={32} className="empty-icon" /><p>Chưa có bàn nào. Nhập khu vực và sức chứa ở trên để thêm bàn đầu tiên.</p></div>}
    </>}
  </div>;
}
