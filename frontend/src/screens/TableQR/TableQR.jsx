import { useNavigate } from 'react-router-dom';
import TableQRGrid from '../../components/TableQRGrid/TableQRGrid';
import styles from './styles.module.css';

// Trang In QR độc lập: dùng lại TableQRGrid (in hàng loạt / chọn bàn, thẻ dán bàn, tải PNG / PDF / zip).
export default function TableQR() {
  const navigate = useNavigate();
  return <div className={styles.page}>
    <header className={`${styles.toolbar} ${styles.noPrint}`}>
      <div className={styles.titleBlock}>
        <button type="button" className={`btn btn-ghost btn-sm ${styles.back}`} onClick={() => navigate(-1)}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>Quay lại</button>
        <h1>Mã QR các bàn</h1>
        <p>Khách quét mã sẽ mở thực đơn đúng bàn. Số bàn chính là id của bàn và nằm trên đường link.</p>
      </div>
    </header>
    <TableQRGrid />
  </div>;
}
