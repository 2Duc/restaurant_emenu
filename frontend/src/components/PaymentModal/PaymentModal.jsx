import { useCallback, useEffect, useRef, useState } from 'react';
import { api, money } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './styles.module.css';

const POLL_MS = 5000;

/**
 * Hộp thoại thanh toán — chỉ xuất hiện khi khách bấm nút "Thanh toán".
 *  - Chuyển khoản: backend tạo link VNPay + ảnh mã QR; màn hình tự kiểm tra kết quả.
 *  - Chuyển khoản ngân hàng: hiện tài khoản nhận + VietQR, chờ nhân viên xác nhận đã nhận tiền.
 *  - Tiền mặt:     báo nhân viên đến thu; chỉ nhân viên xác nhận đã thu, màn hình tự cập nhật.
 */
export default function PaymentModal({ orderId, onClose, onPaid }) {
  const [order, setOrder] = useState(null);
  const [step, setStep] = useState('choose'); // choose | transfer | bank | cash | done
  const [methods, setMethods] = useState(null); // phương thức đang bật (null = chưa biết → hiện như cũ)
  const [payment, setPayment] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const paidNotified = useRef(false);

  // Lấy lại đơn mới nhất (đề phòng đã áp mã giảm giá / gọi thêm món).
  useEffect(() => {
    let active = true;
    api.get(`/orders/${orderId}/`)
      .then(data => active && setOrder(data))
      .catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [orderId]);

  useEffect(() => {
    let active = true;
    api.get('/settings/').then(d => active && setMethods(d?.methods || null)).catch(() => {});
    return () => { active = false; };
  }, []);
  const enabled = m => !methods || methods[m] !== false;

  const markPaid = useCallback((data) => {
    setPayment(data);
    setStep('done');
    if (!paidNotified.current) { paidNotified.current = true; onPaid?.(data); }
  }, [onPaid]);

  async function start(method) {
    setBusy(true); setError('');
    try {
      const data = await api.post('/payments/create/', { order_id: orderId, method });
      if (data.status === 'success') return markPaid(data);
      if (['vnpay', 'bank_transfer'].includes(method) && !data.qr_image) throw new Error('Không nhận được mã QR từ máy chủ.');
      setPayment(data);
      setStep({ vnpay: 'transfer', bank_transfer: 'bank' }[method] || 'cash');
    } catch (e) { setError(e.message || 'Không thể tạo giao dịch.'); }
    finally { setBusy(false); }
  }

  // Tiền mặt: chờ nhân viên xác nhận đã thu tiền.
  useEffect(() => {
    if (!['cash', 'bank'].includes(step) || !payment?.id) return undefined;
    let stopped = false;
    const timer = setInterval(async () => {
      try {
        const data = await api.get(`/payments/${payment.id}/`);
        if (stopped) return;
        if (data.status === 'success') markPaid(data);
        else if (data.status === 'failed') { setPayment(data); setError('Yêu cầu thanh toán đã bị huỷ. Vui lòng thử lại.'); }
        else if (Number(data.amount) !== Number(payment.amount)) setPayment(data);
      } catch { /* thử lại ở lần sau */ }
    }, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [step, payment?.id, payment?.amount, markPaid]);

  // Khi đang hiện QR: định kỳ hỏi backend (backend hỏi lại VNPay) xem đã thanh toán chưa.
  useEffect(() => {
    if (step !== 'transfer' || !payment?.id) return undefined;
    let stopped = false;
    const timer = setInterval(async () => {
      try {
        const data = await api.post(`/payments/${payment.id}/sync/`, {});
        if (stopped) return;
        if (data.status === 'success') markPaid(data);
        else if (data.status === 'failed') { setPayment(data); setError('Giao dịch không thành công. Vui lòng tạo lại mã QR.'); }
      } catch { /* mạng chập chờn: thử lại ở lần sau */ }
    }, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [step, payment?.id, markPaid]);

  const back = () => { setStep('choose'); setError(''); };
  const amount = payment?.amount ?? order?.total_amount;

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && step !== 'done' && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-label="Thanh toán">
        <div className="modal-head">
          <div><span className="modal-eyebrow">THANH TOÁN · ĐƠN #{orderId}</span><h2 className="modal-title">{step === 'done' ? 'Thanh toán thành công' : 'Thanh toán'}</h2></div>
          <button type="button" className="modal-close" onClick={() => onClose()} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button>
        </div>

        <div className={styles.amount}><span>Số tiền cần thanh toán</span>{amount == null ? <span className={`skeleton ${styles.amountSkel}`} aria-hidden="true" /> : <b className="num">{money(amount)}</b>}</div>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}

        {step === 'choose' && (
          <div className={styles.methods}>
            {enabled('vnpay') && <button type="button" disabled={busy || !order} onClick={() => start('vnpay')}>
              <span className={styles.methodIcon}><MaterialIcon name="qr_code_2" size={22} /></span>
              <span><b>Chuyển khoản</b><small>Quét mã QR bằng ứng dụng ngân hàng (VNPay)</small></span>
            </button>}
            {methods?.bank_transfer && <button type="button" disabled={busy || !order} onClick={() => start('bank_transfer')}>
              <span className={styles.methodIcon}><MaterialIcon name="account_balance" size={22} /></span>
              <span><b>Chuyển khoản ngân hàng</b><small>Quét VietQR hoặc chuyển thủ công, nhân viên xác nhận</small></span>
            </button>}
            {enabled('cash') && <button type="button" disabled={busy || !order} onClick={() => start('cash')}>
              <span className={styles.methodIcon}><MaterialIcon name="payments" size={22} /></span>
              <span><b>Tiền mặt</b><small>Trả trực tiếp tại bàn / quầy</small></span>
            </button>}
            {busy && <p className={styles.hint}>Đang tạo giao dịch…</p>}
          </div>
        )}

        {step === 'transfer' && payment && (
          <div className={styles.transfer}>
            <img className={styles.qr} src={payment.qr_image} alt="Mã QR thanh toán VNPay" />
            <p className={styles.hint}>Mở ứng dụng ngân hàng hoặc camera điện thoại, quét mã để thanh toán.</p>
            <p className={styles.waiting}><span className={styles.dot} /> Đang chờ thanh toán…</p>
            <div className={styles.actions}>
              <a className="btn btn-secondary btn-sm" href={payment.pay_url} target="_blank" rel="noreferrer">Mở trang VNPay</a>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => start('vnpay')}>Làm mới mã</button>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={back}>← Chọn hình thức khác</button>
            <small className={styles.sandbox}>Môi trường thử nghiệm VNPay Sandbox — không phải giao dịch tiền thật.</small>
          </div>
        )}

        {step === 'bank' && payment && (
          <div className={styles.transfer}>
            <img className={styles.qr} src={payment.qr_image} alt="Mã VietQR chuyển khoản" />
            <dl className={styles.bank}>
              <div><dt>Ngân hàng</dt><dd>{payment.bank_info?.bank_name || '—'}</dd></div>
              <div><dt>Số tài khoản</dt><dd className="num">{payment.bank_info?.account_no}</dd></div>
              <div><dt>Chủ tài khoản</dt><dd>{payment.bank_info?.account_name}</dd></div>
              <div><dt>Nội dung chuyển khoản</dt><dd className="num">{payment.bank_info?.content}</dd></div>
            </dl>
            <p className={styles.hint}>Quét mã bằng ứng dụng ngân hàng hoặc chuyển khoản đúng số tiền và nội dung. Đã báo nhân viên đối chiếu.</p>
            <p className={styles.waiting}><span className={styles.dot} /> Đang chờ nhân viên xác nhận…</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={back}>← Chọn hình thức khác</button>
          </div>
        )}

        {step === 'cash' && payment && (
          <div className={styles.cash}>
            <p className={styles.hint}>Đã báo nhân viên phục vụ. Vui lòng chuẩn bị <b>{money(amount ?? 0)}</b> tiền mặt — nhân viên sẽ đến thu và xác nhận.</p>
            <p className={styles.waiting}><span className={styles.dot} /> Đang chờ nhân viên xác nhận…</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={back}>← Chọn hình thức khác</button>
          </div>
        )}

        {step === 'done' && (
          <div className={styles.done}>
            <div className={styles.tick}><MaterialIcon name="check" size={32} /></div>
            <p className={styles.hint}>
              Đơn hàng #{orderId} đã được ghi nhận thanh toán{{ vnpay: ' qua VNPay', bank_transfer: ' bằng chuyển khoản ngân hàng' }[payment?.method] || ' bằng tiền mặt'}.
              {payment?.vnp_transaction_no ? <><br />Mã giao dịch VNPay: <b>{payment.vnp_transaction_no}</b></> : null}
            </p>
            <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => onClose()}>Đóng</button>
          </div>
        )}
      </section>
    </div>
  );
}
