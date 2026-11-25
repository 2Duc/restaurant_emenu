import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { login } from '../../services/api';
import styles from './styles.module.css';

export default function LoginScreen() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = await login(username.trim(), password);
      const routes = { PV: '/waiter', BEP: '/chef', QL: '/manager', AD: '/manager' };
      navigate(routes[result.user?.is_superuser ? 'AD' : result.user?.role] || '/manager');
    } catch (e) { setError(e.message || 'Không thể đăng nhập.'); }
    finally { setBusy(false); }
  }
  return <main className={styles.page}>
    <aside className={styles.brandPanel}>
      <div className={styles.brandName}><span className={styles.mono} aria-hidden="true">ABC</span><span>ABC Restaurant</span></div>
      <div>
        <h1>Hương vị Việt, nấu mỗi ngày</h1>
        <p>Quản lý bàn, điều phối món ăn và theo dõi doanh thu trên cùng một hệ thống.</p>
      </div>
      <small>Dành cho nhân viên nhà hàng</small>
    </aside>
    <section className={styles.formPanel}>
      <div className={styles.formBox}>
        <div className={styles.brandMobile}>ABC Restaurant</div>
        <h2>Đăng nhập</h2>
        <p className={styles.sub}>Dành cho nhân viên phục vụ, bếp và quản lý.</p>
        <form onSubmit={submit} className={styles.form}>
          <div className="field">
            <label htmlFor="login-user">Tên đăng nhập</label>
            <input id="login-user" className="input" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} placeholder="Nhập tên đăng nhập" required autoFocus />
          </div>
          <div className="field">
            <label htmlFor="login-pass">Mật khẩu</label>
            <input id="login-pass" className="input" autoComplete="current-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Nhập mật khẩu" required />
          </div>
          {error && <div className="alert alert-danger" role="alert">{error}</div>}
          <button className="btn btn-primary btn-lg btn-block" disabled={busy} aria-busy={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>
        </form>
        <Link to="/" className={styles.back}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>Về thực đơn khách hàng</Link>
      </div>
    </section>
  </main>;
}
