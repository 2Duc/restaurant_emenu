import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const fmt = d => new Date(d).toLocaleString('vi-VN');

// Ngăn trượt "Nhật ký Audit" — dữ liệu thật từ /api/audit-logs/ (ai làm gì, ở chế độ nào).
export default function ManagerAudit({ open, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    api.get('/audit-logs/?limit=200').then(d => { if (active) { setLogs(d); setError(''); setLoaded(true); } }).catch(e => { if (active) { setError(e.message); setLoaded(true); } });
    return () => { active = false; };
  }, [open]);

  function download() {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'audit-log.json'; a.click(); URL.revokeObjectURL(a.href);
  }

  return <aside className={`${ui.drawer} ${open ? ui.drawerOpen : ''}`} aria-hidden={!open} aria-label="Nhật ký thao tác">
    <div className={ui.drawerHead}><div><h3>Nhật ký thao tác</h3><p>Truy vết acted_by / acted_mode</p></div><button className="modal-close" onClick={onClose} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button></div>
    <div className={ui.drawerBody}>
      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      {logs.map(l => <div key={l.id} className={ui.logItem}>
        <div className={ui.logRow}><span>{fmt(l.created_at)}</span><span className="badge badge-neutral">{l.action}</span></div>
        <p>{l.title}</p>
        <pre>{`acted_by: "${l.actor_name}"\nacted_mode: "${l.acted_mode}"${Object.keys(l.payload || {}).length ? `\npayload: ${JSON.stringify(l.payload)}` : ''}`}</pre>
      </div>)}
      {!loaded && !error && <SkeletonRows />}
      {loaded && !logs.length && !error && <div className="empty"><MaterialIcon name="history" size={32} className="empty-icon" /><p>Chưa có thao tác nào được ghi nhận.</p></div>}
    </div>
    <div className={ui.drawerFoot}><button className="btn btn-secondary" onClick={download} disabled={!logs.length}>Tải xuống JSON</button></div>
  </aside>;
}
