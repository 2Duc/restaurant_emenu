import { useEffect, useMemo, useState } from 'react';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './styles.module.css';

/** Nhân viên gọi món hộ khách: thêm vào đơn đang mở của bàn, hoặc mở đơn mới nếu bàn chưa có đơn. */
export default function WaiterAddItems({ table, onClose, onDone }) {
  const [menu, setMenu] = useState([]);
  const [openOrder, setOpenOrder] = useState(null);
  const [cart, setCart] = useState({});          // menu_item id -> { qty, note }
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([api.get('/menu-items/?ordering=name'), api.get(`/tables/${table.id}/current-order/`).catch(() => null)])
      .then(([m, o]) => { if (active) { setMenu((m.results || m).filter(i => i.is_available)); setOpenOrder(o); } })
      .catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [table.id]);

  const shown = useMemo(() => menu.filter(i => i.name.toLowerCase().includes(search.toLowerCase())), [menu, search]);
  const lines = Object.entries(cart).filter(([, v]) => v.qty > 0);
  const total = lines.reduce((n, [id, v]) => n + Number(menu.find(m => m.id === Number(id))?.price || 0) * v.qty, 0);
  const change = (id, delta) => setCart(c => ({ ...c, [id]: { note: '', ...c[id], qty: Math.max(0, (c[id]?.qty || 0) + delta) } }));
  const setNote = (id, note) => setCart(c => ({ ...c, [id]: { qty: 0, ...c[id], note } }));

  async function submit() {
    setBusy(true); setError('');
    try {
      const items = lines.map(([id, v]) => ({ menu_item_id: Number(id), quantity: v.qty, note: (v.note || '').trim() }));
      if (openOrder) await api.post(`/orders/${openOrder.id}/add-items/`, { items });
      else await api.post('/orders/', { table_id: table.id, items });
      await onDone();
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
    <section className={`modal ${styles.modal}`} role="dialog" aria-modal="true" aria-label={`Gọi món cho bàn ${table.id}`}>
      <div className="modal-head"><div><span className="modal-eyebrow">Gọi món hộ khách</span><h2 className="modal-title">Bàn {table.id}{openOrder ? ` · thêm vào đơn #${openOrder.id}` : ' · đơn mới'}</h2></div><button className="modal-close" onClick={onClose} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button></div>
      <input className="input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tìm món" aria-label="Tìm món" />
      <div className={styles.list}>
        {shown.map(item => { const v = cart[item.id]; return <div className={styles.row} key={item.id}>
          {item.image_url?<img className={styles.thumb} src={item.image_url} alt="" loading="lazy"/>:<span className={styles.thumb}><MaterialIcon name="restaurant" size={20}/></span>}
          <div className={styles.info}><b>{item.name}</b><span className="num">{money(item.price)}</span>
            {v?.qty > 0 && <input className="input" value={v.note || ''} maxLength={255} onChange={e => setNote(item.id, e.target.value)} placeholder="Ghi chú cho bếp" aria-label={`Ghi chú ${item.name}`} />}</div>
          <div className={styles.qty}><button onClick={() => change(item.id, -1)} disabled={!v?.qty} aria-label="Giảm"><MaterialIcon name="remove" size={20} /></button><span className="num">{v?.qty || 0}</span><button onClick={() => change(item.id, 1)} aria-label="Tăng"><MaterialIcon name="add" size={20} /></button></div>
        </div>; })}
        {!shown.length && <div className="empty"><p className="empty-title">Không có món phù hợp</p><p>Thử từ khoá khác.</p></div>}
      </div>
      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      <div className={styles.foot}><b className="num">{lines.length} món · {money(total)}</b><button className="btn btn-primary btn-lg" disabled={!lines.length || busy} aria-busy={busy} onClick={submit}>Gửi tới bếp</button></div>
    </section>
  </div>;
}
