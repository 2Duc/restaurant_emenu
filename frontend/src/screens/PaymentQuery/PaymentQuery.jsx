import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, money } from '../../services/api';
import styles from './styles.module.css';

const RESPONSE = { '00': 'Thành công', '91': 'Không tìm thấy giao dịch yêu cầu', '94': 'Yêu cầu bị trùng lặp trong thời gian giới hạn', '97': 'Chữ ký không hợp lệ', '99': 'Lỗi khác' };
const TXN_STATUS = { '00': 'Giao dịch thành công', '01': 'Giao dịch chưa hoàn tất', '02': 'Giao dịch bị lỗi', '04': 'Đã đảo (đã trừ tiền nhưng chưa thành công)', '05': 'VNPay đang xử lý (hoàn tiền)', '06': 'Đã gửi yêu cầu hoàn tiền', '07': 'Giao dịch bị nghi ngờ gian lận', '09': 'Hoàn trả bị từ chối' };
const STATUS = { pending: 'Chờ thanh toán', success: 'Thành công', failed: 'Thất bại', refunded: 'Đã hoàn tiền' };
const FIELDS = [['vnp_TxnRef', 'Mã tham chiếu (TxnRef)'], ['vnp_TransactionNo', 'Mã giao dịch VNPay'], ['vnp_BankCode', 'Ngân hàng'], ['vnp_PayDate', 'Thời gian thanh toán'], ['vnp_OrderInfo', 'Nội dung']];

// Tra cứu giao dịch VNPay (API querydr) — tương ứng query.html của dự án mẫu.
export default function PaymentQuery() {
  const navigate = useNavigate();
  const [orderId, setOrderId] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setResult(null);
    try { setResult(await api.post('/payments/query/', { order_id: Number(orderId) })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const v = result?.vnpay; const p = result?.payment;
  return <main className={styles.page}><div className={styles.wrap}>
    <button type="button" className={`btn btn-ghost btn-sm ${styles.back}`} onClick={() => navigate(-1)}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>Quay lại</button>
    <header className={styles.head}>
      <h1>Tra cứu giao dịch</h1>
      <p>Kiểm tra trạng thái thanh toán của một đơn hàng, đối chiếu với VNPay (môi trường thử nghiệm).</p>
    </header>
    <form onSubmit={submit} className={`card ${styles.form}`}>
      <div className="field">
        <label htmlFor="pq-order">Mã đơn hàng</label>
        <input id="pq-order" className="input num" type="number" min="1" required inputMode="numeric" value={orderId} onChange={e => setOrderId(e.target.value)} placeholder="Ví dụ: 15" />
      </div>
      <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? 'Đang tra cứu…' : 'Tra cứu'}</button>
    </form>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {busy && <div className={`card ${styles.result}`} aria-hidden="true"><span className="skeleton" style={{ width: '40%' }} /><span className="skeleton" /><span className="skeleton" style={{ width: '70%' }} /></div>}
    {p && <section className={`card ${styles.result}`}>
      <h2>Giao dịch trong hệ thống</h2>
      <dl><dt>Mã giao dịch</dt><dd className="num">#{p.id}</dd><dt>Hình thức</dt><dd>{{ vnpay: 'Chuyển khoản (VNPay)', bank_transfer: 'Chuyển khoản ngân hàng' }[p.method] || 'Tiền mặt'}</dd><dt>Số tiền</dt><dd className="num">{money(p.amount)}</dd><dt>Trạng thái</dt><dd>{STATUS[p.status] || p.status}</dd>{Number(p.refunded_amount) > 0 && <><dt>Đã hoàn</dt><dd className="num">{money(p.refunded_amount)}</dd></>}</dl>
      {result.detail && <p className={styles.note}>{result.detail}</p>}
    </section>}
    {v && <section className={`card ${styles.result}`}>
      <h2>Kết quả từ VNPay</h2>
      <dl>
        <dt>Phản hồi API</dt><dd>{v.vnp_ResponseCode} — {RESPONSE[v.vnp_ResponseCode] || v.vnp_Message || 'Không rõ'}</dd>
        {v.vnp_TransactionStatus && <><dt>Trạng thái giao dịch</dt><dd>{v.vnp_TransactionStatus} — {TXN_STATUS[v.vnp_TransactionStatus] || 'Không rõ'}</dd></>}
        {v.vnp_Amount && <><dt>Số tiền</dt><dd className="num">{money(Number(v.vnp_Amount) / 100)}</dd></>}
        {FIELDS.filter(([k]) => v[k]).map(([k, label]) => <div key={k} className={styles.row}><dt>{label}</dt><dd className="num">{v[k]}</dd></div>)}
      </dl>
    </section>}
  </div></main>;
}
