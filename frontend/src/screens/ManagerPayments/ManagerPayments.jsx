import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const STATUS = { pending: ['Chờ', 'badge-warn'], success: ['Thành công', 'badge-ok'], failed: ['Thất bại', 'badge-danger'], refunded: ['Đã hoàn', 'badge-neutral'] };
const METHOD = { cash: 'Tiền mặt', vnpay: 'VNPay', bank_transfer: 'Chuyển khoản ngân hàng', momo: 'MoMo', zalopay: 'ZaloPay' };
const fmt = d => d ? new Date(d).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'medium' }) : '—';

export default function ManagerPayments({ refreshKey = 0 }) {
  const [filters, setFilters] = useState({ method: '', status: '', date_from: '', date_to: '' });
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let active = true;
    const qs = new URLSearchParams({ limit: '500' });
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
    api.get(`/payments/?${qs}`).then(d => { if (active) { setRows(d); setError(''); setLoaded(true); } }).catch(e => { if (active) { setError(e.message); setLoaded(true); } });
    return () => { active = false; };
  }, [filters, tick, refreshKey]);

  const totals = useMemo(() => {
    const ok = rows.filter(r => ['success', 'refunded'].includes(r.status));
    return { gross: ok.reduce((n, r) => n + Number(r.amount), 0), refunded: ok.reduce((n, r) => n + Number(r.refunded_amount), 0), count: ok.length };
  }, [rows]);
  const set = (k, v) => setFilters(f => ({ ...f, [k]: v }));

  function exportCsv() {
    const head = ['Mã GD', 'Đơn', 'Bàn', 'Hình thức', 'Số tiền', 'Đã hoàn', 'Trạng thái', 'Mã tham chiếu', 'Mã GD VNPay', 'Ngân hàng', 'Tạo lúc', 'Thanh toán lúc'];
    const lines = rows.map(r => [r.id, r.order, r.table_id, METHOD[r.method] || r.method, r.amount, r.refunded_amount, r.status, r.transaction_id, r.vnp_transaction_no, r.vnp_bank_code, r.created_at, r.paid_at || ''].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    const blob = new Blob(['\ufeff' + [head.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `doi-soat-${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(a.href);
  }

  return <div className={ui.panel}>
    <div className={ui.head}><p className={ui.lead}>Dữ liệu thật từ bảng thanh toán (VNPay sandbox và tiền mặt).</p>
      <div className={ui.headActions}><Link className="btn btn-secondary" to="/payments/query">Tra cứu VNPay</Link><Link className="btn btn-secondary" to="/payments/refund">Hoàn tiền</Link><button className="btn btn-primary" onClick={exportCsv} disabled={!rows.length}><MaterialIcon name="download" size={18} />Xuất CSV</button></div></div>
    <div className={ui.kpis}>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Giao dịch thành công</span><b className={ui.kpiValue}>{totals.count}</b></div>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Tổng thu</span><b className={ui.kpiValue}>{money(totals.gross)}</b></div>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Đã hoàn</span><b className={ui.kpiValue}>{money(totals.refunded)}</b></div>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Thực thu</span><b className={ui.kpiValue}>{money(totals.gross - totals.refunded)}</b></div>
    </div>
    <div className={`card ${ui.toolbar}`}>
      <label className="field"><span className="field-label">Hình thức</span><select className="select" value={filters.method} onChange={e => set('method', e.target.value)}><option value="">Tất cả</option><option value="cash">Tiền mặt</option><option value="vnpay">VNPay</option><option value="bank_transfer">Chuyển khoản ngân hàng</option></select></label>
      <label className="field"><span className="field-label">Trạng thái</span><select className="select" value={filters.status} onChange={e => set('status', e.target.value)}><option value="">Tất cả</option>{Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="field"><span className="field-label">Từ ngày</span><input className="input" type="date" value={filters.date_from} onChange={e => set('date_from', e.target.value)} /></label>
      <label className="field"><span className="field-label">Đến ngày</span><input className="input" type="date" value={filters.date_to} onChange={e => set('date_to', e.target.value)} /></label>
      <button className="btn btn-secondary" onClick={() => setTick(t => t + 1)}><MaterialIcon name="refresh" size={18} />Làm mới</button>
    </div>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    <div className="table-wrap"><table className="table">
      <thead><tr><th>GD</th><th>Đơn · Bàn</th><th>Hình thức</th><th className="num">Số tiền</th><th>Trạng thái</th><th>Mã VNPay</th><th>Ngân hàng</th><th>Thời gian</th></tr></thead>
      <tbody>{rows.map(r => { const [l, c] = STATUS[r.status] || [r.status, 'badge-neutral']; return <tr key={r.id}>
        <td>#{r.id}</td><td>#{r.order} · Bàn {r.table_id}</td><td>{METHOD[r.method] || r.method}</td>
        <td className="num">{money(r.amount)}{Number(r.refunded_amount) > 0 && <div className={ui.refundNote}>hoàn {money(r.refunded_amount)}</div>}</td>
        <td><span className={`badge ${c}`}>{l}</span></td><td>{r.vnp_transaction_no || '—'}</td><td>{r.vnp_bank_code || '—'}</td><td>{fmt(r.paid_at || r.created_at)}</td></tr>; })}</tbody>
    </table>{!loaded ? <SkeletonRows /> : !rows.length && <div className="empty"><MaterialIcon name="account_balance_wallet" size={32} className="empty-icon" /><p>Chưa có giao dịch nào khớp bộ lọc.</p></div>}</div>
  </div>;
}
