import { Link } from 'react-router-dom';
import { getAccessToken, getRole, HOME_BY_ROLE } from '../../services/api';
import styles from './styles.module.css';

// Hiện khi đường dẫn không tồn tại (thay cho việc tự chuyển hướng âm thầm).
export default function NotFound() {
  const role = getAccessToken() ? getRole() : null;
  return <main className={styles.page}><section className={styles.card}>
    <div className={styles.icon}><span className="material-symbols-outlined" aria-hidden="true">search_off</span></div>
    <h1>Không tìm thấy trang</h1>
    <p>Đường dẫn này không tồn tại hoặc đã được thay đổi.</p>
    <div className={styles.actions}>
      <Link className="btn btn-primary" to="/table/1">Về thực đơn</Link>
      {role ? <Link className="btn btn-secondary" to={HOME_BY_ROLE[role] || '/login'}>Về trang làm việc</Link> : <Link className="btn btn-secondary" to="/login">Đăng nhập nhân viên</Link>}
    </div>
  </section></main>;
}
