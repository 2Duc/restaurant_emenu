import { Link, useSearchParams } from 'react-router-dom';
import styles from './PaymentResult.module.css';
export default function PaymentResult(){
 const [params]=useSearchParams(); const status=params.get('status'); const order=params.get('order'); const table=params.get('table');
 const ok=status==='success';
 return <main className={styles.page}><section className={styles.card} role="status">
  <div className={`${styles.icon} ${ok?styles.success:styles.failed}`}><span className="material-symbols-outlined" aria-hidden="true">{ok?'check':'priority_high'}</span></div>
  <h1>{ok?'Thanh toán thành công':'Chưa xác nhận thanh toán'}</h1>
  <p>{ok?`Đơn #${order||''} đã được ghi nhận thanh toán.`:'Giao dịch không thành công hoặc chưa xác thực được. Vui lòng hỏi nhân viên để kiểm tra lại.'}</p>
  <small>Môi trường thử nghiệm VNPay, không phải giao dịch tiền thật.</small>
  <Link className="btn btn-primary btn-lg" to={/^\d+$/.test(table||'')?`/table/${table}`:`/menu?table=12`}>Quay lại thực đơn</Link>
 </section></main>;
}
