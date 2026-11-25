import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, money } from '../../services/api';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const STATUS = { pending: ['Chờ xử lý', 'badge-warn'], confirmed: ['Đã xác nhận', 'badge-warn'], completed: ['Hoàn thành', 'badge-ok'], cancelled: ['Đã huỷ', 'badge-neutral'] };
const PAY = { pending: 'Chờ thanh toán', success: 'Đã thanh toán', failed: 'Thất bại', refunded: 'Đã hoàn tiền' };
const METHOD = { cash: 'Tiền mặt', vnpay: 'Chuyển khoản (VNPay)' };
const ITEM = { pending: 'Chờ bếp', cooking: 'Đang chế biến', done: 'Đã xong', served: 'Đã phục vụ' };
const fmt = d => new Date(d).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });

export default function ManagerOrders({ refreshKey = 0 }) {
  const [confirm, confirmDialog] = useConfirm();
  const [filters, setFilters] = useState({ status: '', date_from: '', date_to: '', q: '' });
  const [orders, setOrders] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const PAGE_SIZE = 20;

  useEffect(() => {
    let active = true;
    const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
    api.get(`/orders/?${qs}`)
      .then(d => { if (active) { setOrders(d.results || d); setCount(d.count ?? (d.results || d).length); setHasNext(!!d.next); setError(''); setLoaded(true); } })
      .catch(e => { if (active) { setError(e.message); setLoaded(true); } });
    return () => { active = false; };
  }, [filters, tick, refreshKey, page]);

  const set = (k, v) => { setPage(1); setFilters(f => ({ ...f, [k]: v })); };
  async function changeStatus(order, status) {
    if (status === 'cancelled' && !await confirm(`Huỷ đơn #${order.id}?`, { danger: true, confirmLabel: 'Huỷ đơn' })) return;
    try { const o = await api.patch(`/orders/${order.id}/status/`, { status }); setSelected({ ...order, ...o }); setTick(t => t + 1); }
    catch (e) { setError(e.message); }
  }

  return <div className={ui.panel}>
    <div className={ui.head}><p className={ui.lead}>{count} đơn theo bộ lọc hiện tại</p>
      <button className="btn btn-secondary" onClick={() => setTick(t => t + 1)}><MaterialIcon name="refresh" size={18} />Làm mới</button></div>
    <div className={`card ${ui.toolbar}`}>
      <label className="field"><span className="field-label">Mã đơn</span><input className="input" type="number" min="1" value={filters.q} onChange={e => set('q', e.target.value)} placeholder="VD: 15" /></label>
      <label className="field"><span className="field-label">Trạng thái</span><select className="select" value={filters.status} onChange={e => set('status', e.target.value)}><option value="">Tất cả</option>{Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="field"><span className="field-label">Từ ngày</span><input className="input" type="date" value={filters.date_from} onChange={e => set('date_from', e.target.value)} /></label>
      <label className="field"><span className="field-label">Đến ngày</span><input className="input" type="date" value={filters.date_to} onChange={e => set('date_to', e.target.value)} /></label>
      <button className="btn btn-ghost" onClick={() => { setPage(1); setFilters({ status: '', date_from: '', date_to: '', q: '' }); }}>Xoá lọc</button>
    </div>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Đơn</th><th>Bàn</th><th>Thời gian</th><th className="num">Số món</th><th className="num">Tổng tiền</th><th>Đơn hàng</th><th>Thanh toán</th><th /></tr></thead>
      <tbody>{orders.map(o => { const [label, cls] = STATUS[o.status] || [o.status, 'badge-neutral']; return <tr key={o.id}>
        <td><b>#{o.id}</b></td><td>{o.table_number}</td><td>{fmt(o.created_at)}</td><td className="num">{o.items?.length || 0}</td><td className="num">{money(o.total_amount)}</td>
        <td><span className={`badge ${cls}`}>{label}</span></td>
        <td>{o.payment_status ? `${PAY[o.payment_status]} · ${METHOD[o.payment_method] || o.payment_method}` : '—'}</td>
        <td><div className={ui.rowActions}><button className="btn btn-secondary btn-sm" onClick={() => setSelected(o)}>Hóa đơn</button></div></td></tr>; })}</tbody>
    </table>{!loaded ? <SkeletonRows /> : !orders.length && <div className="empty"><MaterialIcon name="receipt_long" size={32} className="empty-icon" /><p>Không có đơn hàng nào khớp bộ lọc.</p></div>}</div>

    {(page > 1 || hasNext) && <div className={ui.head}>
      <button className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><MaterialIcon name="chevron_left" size={18} />Trang trước</button>
      <span className={ui.lead}>Trang {page}</span>
      <button className="btn btn-secondary btn-sm" disabled={!hasNext} onClick={() => setPage(p => p + 1)}>Trang sau<MaterialIcon name="chevron_right" size={18} /></button>
    </div>}

    {selected && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setSelected(null)}><section className={`modal ${ui.invoice}`}>
      <div className="modal-head"><h3 className="modal-title">Hóa đơn #{selected.id} · Bàn {selected.table_number}</h3><button className="modal-close" aria-label="Đóng" onClick={() => setSelected(null)}><MaterialIcon name="close" size={20} /></button></div>
      <p className={ui.invoiceMeta}>Tạo lúc {fmt(selected.created_at)}</p>
      <div className="table-wrap"><table className="table"><thead><tr><th>Món</th><th className="num">SL</th><th className="num">Đơn giá</th><th className="num">Thành tiền</th></tr></thead>
        <tbody>{selected.items?.map(i => <tr key={i.id}><td>{i.menu_item_name}{i.note && <div className={ui.itemNote}>Ghi chú: {i.note}</div>}<div className={ui.itemNote}>{ITEM[i.status]}</div></td><td className="num">{i.quantity}</td><td className="num">{money(i.unit_price)}</td><td className="num">{money(i.quantity * i.unit_price)}</td></tr>)}</tbody></table></div>
      <div className={ui.sums}>
        <div className={ui.sum}><span>Tạm tính</span><span>{money(selected.subtotal_amount)}</span></div>
        {Number(selected.discount_amount) > 0 && <div className={ui.sum}><span>Giảm giá {selected.promotion_code && `(${selected.promotion_code})`}</span><span>−{money(selected.discount_amount)}</span></div>}
        <div className={`${ui.sum} ${ui.total}`}><span>Tổng thanh toán</span><span>{money(selected.total_amount)}</span></div>
      </div>
      <p className={ui.invoiceMeta}>Thanh toán: {selected.payment_status ? `${PAY[selected.payment_status]} (${METHOD[selected.payment_method] || selected.payment_method})` : 'chưa có giao dịch'}</p>
      <div className="modal-foot">
        {['pending', 'confirmed'].includes(selected.status) && <button className="btn btn-ghost" onClick={() => changeStatus(selected, 'cancelled')}>Huỷ đơn</button>}
        {selected.payment_method === 'vnpay' && selected.payment_status === 'success' && <Link className="btn btn-secondary" to="/payments/refund">Hoàn tiền</Link>}
        <button className="btn btn-primary" onClick={() => window.print()}>In hóa đơn</button>
      </div>
    </section></div>}
    {confirmDialog}
  </div>;
}
