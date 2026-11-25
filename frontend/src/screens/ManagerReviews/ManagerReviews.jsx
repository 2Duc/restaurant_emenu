import { useEffect, useMemo, useState } from 'react';
import { api } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const stars = n => '★'.repeat(n) + '☆'.repeat(5 - n);
const fmt = d => new Date(d).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });

export default function ManagerReviews({ refreshKey = 0 }) {
  const [reviews, setReviews] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [rating, setRating] = useState('');
  const [dish, setDish] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/reviews/${rating ? `?rating=${rating}` : ''}`)
      .then(d => { if (active) { setReviews(d.results || d); setError(''); setLoaded(true); } })
      .catch(e => { if (active) { setError(e.message); setLoaded(true); } });
    return () => { active = false; };
  }, [rating, refreshKey]);

  const perDish = useMemo(() => {
    const map = new Map();
    reviews.forEach(r => { const x = map.get(r.menu_item) || { id: r.menu_item, name: r.menu_item_name, sum: 0, count: 0 }; x.sum += r.rating; x.count += 1; map.set(r.menu_item, x); });
    return [...map.values()].map(x => ({ ...x, avg: x.sum / x.count })).sort((a, b) => b.count - a.count);
  }, [reviews]);
  const shown = dish ? reviews.filter(r => String(r.menu_item) === dish) : reviews;
  const avgAll = reviews.length ? reviews.reduce((n, r) => n + r.rating, 0) / reviews.length : 0;

  return <div className={ui.panel}>
    <div className={ui.head}><p className={ui.lead}>200 đánh giá gần nhất theo bộ lọc hiện tại.</p></div>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    <div className={ui.kpis}>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Số đánh giá</span><b className={ui.kpiValue}>{reviews.length}</b></div>
      <div className={ui.kpi}><span className={ui.kpiLabel}>Điểm trung bình</span><b className={ui.kpiValue}>{reviews.length ? avgAll.toFixed(1) : '—'} <span className={ui.stars}>★</span></b></div>
    </div>
    <div className={ui.grid2}>
      <div className="card"><h3 className={ui.sectionTitle}>Theo món</h3>
        {perDish.length ? <div className={ui.bars}>{perDish.map(d => <div className={ui.barRow} key={d.id}>
          <button className={ui.link} onClick={() => setDish(String(d.id) === dish ? '' : String(d.id))} aria-pressed={String(d.id) === dish}>{d.name}</button>
          <div className={ui.barTrack}><div className={ui.barFill} style={{ width: `${(d.avg / 5) * 100}%` }} /></div><b>{d.avg.toFixed(1)} ★ · {d.count}</b>
        </div>)}</div> : !loaded ? <SkeletonRows /> : <div className="empty"><MaterialIcon name="reviews" size={32} className="empty-icon" /><p>Chưa có đánh giá nào từ khách.</p></div>}
      </div>
      <div className="card">
        <div className={ui.toolbar}>
          <label className="field"><span className="field-label">Số sao</span><select className="select" value={rating} onChange={e => setRating(e.target.value)}><option value="">Tất cả</option>{[5, 4, 3, 2, 1].map(n => <option key={n} value={n}>{n} sao</option>)}</select></label>
          {dish && <button className="btn btn-ghost" onClick={() => setDish('')}>Bỏ lọc món</button>}
        </div>
        <div className={ui.reviewList}>{shown.map(r => <article key={r.id} className={ui.review}>
          <div className={ui.reviewTop}><b>{r.menu_item_name}</b><span className={ui.stars} aria-label={`${r.rating} sao`}>{stars(r.rating)}</span></div>
          {r.comment && <p>“{r.comment}”</p>}
          <small>Bàn {r.table_id} · Đơn #{r.order} · {fmt(r.created_at)}</small>
        </article>)}{!shown.length && <div className="empty"><p>Không có đánh giá phù hợp bộ lọc.</p></div>}</div>
      </div>
    </div>
  </div>;
}
