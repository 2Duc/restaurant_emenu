import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './MockGateway.module.css';

export default function MockGateway() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const txn = params.get('txn') || '';
  const amount = params.get('amount');
  const order = params.get('order') || '';
  const table = params.get('table') || '';
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function submit(result) {
    setBusy(result); setError('');
    try {
      const data = await api.post('/payments/mock-callback/', { txn_ref: txn, result });
      navigate(`/payment-result?status=${data.status}&order=${order || data.payment?.order || ''}&table=${table}`);
    } catch (e) { setError(e.message || 'Không thể xử lý giao dịch.'); setBusy(''); }
  }

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <span className={styles.badge}>CỔNG THANH TOÁN GIẢ LẬP</span>
        <h1>ABC Restaurant</h1>
        <div className={styles.amount}><span>Số tiền thanh toán</span><b className="num">{money(amount)}</b></div>
        <dl className={styles.meta}>
          <div><dt>Mã giao dịch</dt><dd>{txn || '—'}</dd></div>
          {order && <div><dt>Đơn hàng</dt><dd>#{order}</dd></div>}
        </dl>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <button type="button" className="btn btn-primary btn-lg btn-block" disabled={!txn || !!busy} onClick={() => submit('success')}>
          <MaterialIcon name="check_circle" size={20} /> Thanh toán thành công
        </button>
        <button type="button" className="btn btn-secondary btn-lg btn-block" disabled={!txn || !!busy} onClick={() => submit('cancel')}>
          <MaterialIcon name="cancel" size={20} /> Huỷ giao dịch
        </button>
        <small>Môi trường thử nghiệm, không phải giao dịch tiền thật.</small>
      </section>
    </main>
  );
}
