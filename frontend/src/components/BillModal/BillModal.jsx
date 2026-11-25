import { useEffect, useState } from 'react';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './styles.module.css';

const ITEM_STATUS = { pending: 'Chờ bếp', cooking: 'Đang chế biến', done: 'Đã xong', served: 'Đã phục vụ' };

/** Hóa đơn tạm tính của đơn đang mở: từng món, tạm tính, giảm giá, tổng. */
export default function BillModal({ order, onClose, onPay }) {
  const [note, setNote] = useState('');
  useEffect(() => { let on = true; api.get('/settings/').then(s => on && setNote(s?.invoice_note || '')).catch(() => {}); return () => { on = false; }; }, []);
  const open = !['completed', 'cancelled'].includes(order.status);
  const discount = Number(order.discount_amount || 0);
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-label="Hóa đơn tạm tính">
        <div className="modal-head">
          <div><span className="modal-eyebrow">{open ? 'HÓA ĐƠN TẠM TÍNH' : 'HÓA ĐƠN'} · BÀN {order.table_number}</span><h2 className="modal-title">Đơn #{order.id}</h2></div>
          <button className="modal-close" onClick={onClose} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button>
        </div>
        <div className={styles.lines}>
          {order.items?.map(i => <div className={styles.line} key={i.id}>
            <div><b>{i.quantity} × {i.menu_item_name}</b>
              {i.note && <small>Ghi chú: {i.note}</small>}
              <small>{money(i.unit_price)} / phần · {ITEM_STATUS[i.status] || i.status}</small></div>
            <b className="num">{money(Number(i.unit_price) * i.quantity)}</b>
          </div>)}
        </div>
        <div className={styles.sum}><span>Tạm tính</span><b className="num">{money(order.subtotal_amount)}</b></div>
        {discount > 0 && <div className={styles.sum}><span>Giảm giá{order.promotion_code ? ` (${order.promotion_code})` : ''}</span><b className={`${styles.minus} num`}>−{money(discount)}</b></div>}
        <div className={`${styles.sum} ${styles.total}`}><span>Tổng cộng</span><b className="num">{money(order.total_amount)}</b></div>
        {note && <p className={styles.note}>{note}</p>}
        {open && <button className="btn btn-primary btn-lg btn-block" onClick={() => { onClose(); onPay(); }}>Thanh toán ngay</button>}
        {!open && <p className={`${styles.paid} ${order.status === 'completed' ? styles.paidOk : styles.paidOff}`}>{order.status === 'completed' ? 'Đơn đã thanh toán — cảm ơn quý khách!' : 'Đơn đã huỷ.'}</p>}
      </section>
    </div>
  );
}
