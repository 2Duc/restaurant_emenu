import { useEffect, useState } from 'react';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import m from '../Manager/styles.module.css';

const PERIODS = [['day', 'Hôm nay'], ['week', '7 ngày'], ['month', '30 ngày'], ['custom', 'Tuỳ chọn']];
const METHOD = { cash: 'Tiền mặt', vnpay: 'Chuyển khoản (VNPay)', bank_transfer: 'Chuyển khoản ngân hàng', momo: 'MoMo', zalopay: 'ZaloPay' };
const short = v => v >= 1e6 ? `${(v / 1e6).toFixed(1)}tr` : v >= 1e3 ? `${Math.round(v / 1e3)}k` : String(v);

function Column({ items, valueKey, labelEvery }) {
  const max = Math.max(1, ...items.map(i => i[valueKey]));
  return <div className={m.chart}>
    {[0, 25, 50, 75].map(t => <div key={t} className={m.gridLine} style={{ top: `calc((100% - 20px) * ${t / 100})` }} />)}
    <div className={m.columns}>{items.map((i, idx) => <div key={i.label || i.hour} className={m.col} title={`${i.label ?? `${i.hour}h`}: ${valueKey === 'total' ? money(i[valueKey]) : `${i[valueKey]} đơn`}`}>
      <div className={m.colBar} style={{ height: `${Math.max(2, (i[valueKey] / max) * 100)}%`, opacity: i[valueKey] ? 1 : .25 }} />
      <span className={m.colLabel}>{idx % labelEvery === 0 ? (i.label ?? `${i.hour}h`) : ''}</span>
    </div>)}</div>
    <div className={m.gridLine} style={{ bottom: 20 }} />
  </div>;
}

export default function ManagerReports({ refreshKey = 0 }) {
  const today = new Date().toISOString().slice(0, 10);
  const [period, setPeriod] = useState('month');
  const [range, setRange] = useState({ from: today, to: today });
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const qs = period === 'custom' ? `date_from=${range.from}&date_to=${range.to}` : `period=${period}`;
    api.get(`/reports/summary/?${qs}`)
      .then(d => { if (active) { setData(d); setError(''); } })
      .catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [period, range, refreshKey]);

  const maxQty = Math.max(1, ...(data?.best_sellers || []).map(b => b.quantity));
  const totalMethods = Math.max(1, ...(data?.methods || []).map(m => m.total));
  const peak = data ? [...data.peak_hours].sort((a, b) => b.orders - a.orders)[0] : null;

  return <div className={m.panel}>
    <div className={m.head}>
      <p className={m.lead}>Doanh thu tính theo giao dịch thành công, đã trừ tiền hoàn.{data && ` Kỳ: ${data.date_from} → ${data.date_to}`}</p>
      <div className={m.toolbar}>
        <div className="tabs" role="tablist" aria-label="Kỳ báo cáo">{PERIODS.map(([k, label]) => <button key={k} role="tab" aria-selected={period === k} onClick={() => setPeriod(k)}>{label}</button>)}</div>
        {period === 'custom' && <>
          <label className="field"><span className="field-label">Từ ngày</span><input className="input" type="date" value={range.from} max={range.to} onChange={e => setRange(r => ({ ...r, from: e.target.value }))} /></label>
          <label className="field"><span className="field-label">Đến ngày</span><input className="input" type="date" value={range.to} min={range.from} onChange={e => setRange(r => ({ ...r, to: e.target.value }))} /></label>
        </>}
      </div>
    </div>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {!data && !error && <>
      <div className={m.kpis}>{[0, 1, 2, 3].map(i => <div key={i} className={`skeleton ${m.skelKpi}`} />)}</div>
      <div className={`skeleton ${m.skelBlock}`} />
    </>}
    {data && <>
      <div className={m.kpis}>
        <div className={m.kpi}><span className={m.kpiLabel}>Doanh thu</span><b className={m.kpiValue}>{money(data.revenue)}</b><span className={m.kpiNote}>Đã trừ tiền hoàn</span></div>
        <div className={m.kpi}><span className={m.kpiLabel}>Đơn đã thanh toán</span><b className={m.kpiValue}>{data.paid_orders}</b><span className={m.kpiNote}>{data.pending_orders} đơn đang mở</span></div>
        <div className={m.kpi}><span className={m.kpiLabel}>Giá trị TB / đơn</span><b className={m.kpiValue}>{money(data.avg_order)}</b><span className={m.kpiNote}>Trên đơn đã thanh toán</span></div>
        <div className={m.kpi}><span className={m.kpiLabel}>Đã hoàn tiền</span><b className={m.kpiValue}>{money(data.refunded)}</b><span className={m.kpiNote}>Trong kỳ đang xem</span></div>
      </div>
      <div className="card"><h3 className={m.sectionTitle}>Doanh thu theo {period === 'day' ? 'giờ' : 'ngày'}</h3>
        {data.paid_orders ? <Column items={data.series} valueKey="total" labelEvery={period === 'day' ? 3 : Math.ceil(data.series.length / 10)} /> : <div className="empty"><MaterialIcon name="bar_chart" size={32} className="empty-icon" /><p>Chưa có giao dịch trong kỳ này.</p></div>}
        {data.paid_orders > 0 && <small className={m.axis}>Cột cao nhất ≈ {short(Math.max(...data.series.map(s => s.total)))}đ</small>}
      </div>
      <div className={m.grid2}>
        <div className="card"><h3 className={m.sectionTitle}>Món bán chạy</h3>
          {data.best_sellers.length ? <div className={m.bars}>{data.best_sellers.map(b => <div className={m.barRow} key={b.id}>
            <span>{b.name}</span><div className={m.barTrack}><div className={m.barFill} style={{ width: `${(b.quantity / maxQty) * 100}%` }} /></div><b>{b.quantity} · {short(b.revenue)}đ</b>
          </div>)}</div> : <div className="empty"><MaterialIcon name="restaurant_menu" size={32} className="empty-icon" /><p>Chưa có món nào được bán trong kỳ này.</p></div>}
        </div>
        <div className="card"><h3 className={m.sectionTitle}>Khung giờ cao điểm {peak?.orders > 0 && <span className="badge badge-brand">Cao nhất: {peak.hour}h–{peak.hour + 1}h · {peak.orders} đơn</span>}</h3>
          {data.paid_orders ? <Column items={data.peak_hours} valueKey="orders" labelEvery={3} /> : <div className="empty"><MaterialIcon name="schedule" size={32} className="empty-icon" /><p>Chưa có đơn nào để thống kê giờ cao điểm.</p></div>}
        </div>
      </div>
      <div className="card"><h3 className={m.sectionTitle}>Theo hình thức thanh toán</h3>
        {data.methods.length ? <div className={m.bars}>{data.methods.map(x => <div className={m.barRow} key={x.method}>
          <span>{METHOD[x.method] || x.method}</span><div className={m.barTrack}><div className={m.barFill} style={{ width: `${(x.total / totalMethods) * 100}%` }} /></div><b>{money(x.total)} · {x.orders} đơn</b>
        </div>)}</div> : <div className="empty"><MaterialIcon name="payments" size={32} className="empty-icon" /><p>Chưa có giao dịch nào trong kỳ này.</p></div>}
      </div>
    </>}
  </div>;
}
