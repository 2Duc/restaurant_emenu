import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './styles.module.css';

/** Khách đánh giá (1–5 sao + nhận xét) các món đã được phục vụ của đơn đã thanh toán. */
export default function ReviewModal({ order, onClose, onReviewed }) {
  const [reviews, setReviews] = useState({});   // order_item id -> review đã gửi
  const [drafts, setDrafts] = useState({});     // order_item id -> {rating, comment}
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/reviews/?order_id=${order.id}`).then(list => {
      if (active) setReviews(Object.fromEntries((list.results || list).map(r => [r.order_item, r])));
    }).catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [order.id]);

  const served = order.items?.filter(i => i.status === 'served') || [];
  const waiting = (order.items?.length || 0) - served.length;
  const setDraft = (id, patch) => setDrafts(d => ({ ...d, [id]: { rating: 0, comment: '', ...d[id], ...patch } }));

  async function submit(item) {
    const d = drafts[item.id];
    if (!d?.rating) { setError('Vui lòng chọn số sao trước khi gửi.'); return; }
    setBusyId(item.id); setError('');
    try {
      const r = await api.post('/reviews/', { order_item: item.id, rating: d.rating, comment: d.comment || '' });
      setReviews(prev => ({ ...prev, [item.id]: r }));
      onReviewed?.(r);
    } catch (e) { setError(e.message); } finally { setBusyId(null); }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-label="Đánh giá món">
        <div className="modal-head"><div><span className="modal-eyebrow">ĐƠN #{order.id}</span><h2 className="modal-title">Đánh giá món ăn</h2></div><button className="modal-close" onClick={onClose} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button></div>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        {!served.length && <p className={styles.hint}>Chưa có món nào được phục vụ để đánh giá.</p>}
        {served.map(item => {
          const done = reviews[item.id]; const d = drafts[item.id] || { rating: 0, comment: '' };
          const shown = done ? done.rating : d.rating;
          return <div className={styles.item} key={item.id}>
            <b>{item.menu_item_name}</b>
            <div className={styles.stars} role="radiogroup" aria-label={`Đánh giá ${item.menu_item_name}`}>
              {[1, 2, 3, 4, 5].map(n => <button key={n} type="button" disabled={!!done} className={n <= shown ? styles.on : ''} onClick={() => setDraft(item.id, { rating: n })} aria-label={`${n} sao`}><MaterialIcon name="star" filled size={28} /></button>)}
            </div>
            {done ? <p className={styles.thanks}>Cảm ơn bạn đã đánh giá!{done.comment && <><br /><i>“{done.comment}”</i></>}</p> : <>
              <textarea className="textarea" placeholder="Nhận xét của bạn (không bắt buộc)" maxLength={300} value={d.comment} onChange={e => setDraft(item.id, { comment: e.target.value })} />
              <button className={`btn btn-primary btn-sm ${styles.send}`} aria-busy={busyId === item.id} disabled={busyId === item.id} onClick={() => submit(item)}>{busyId === item.id ? 'Đang gửi…' : 'Gửi đánh giá'}</button>
            </>}
          </div>;
        })}
        {waiting > 0 && served.length > 0 && <p className={styles.hint}>{waiting} món chưa được phục vụ nên chưa thể đánh giá.</p>}
      </section>
    </div>
  );
}
