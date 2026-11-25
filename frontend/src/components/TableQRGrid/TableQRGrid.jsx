import { useEffect, useMemo, useState } from 'react';
import { api, saveFile } from '../../services/api';
import styles from './styles.module.css';

/**
 * Màn In QR: thẻ dán bàn (tên quán, số bàn, QR lớn, dòng hướng dẫn quét), in hàng loạt / chọn bàn,
 * tải PNG từng bàn, tải tất cả (PDF A4 4 thẻ/trang hoặc zip). QR dùng lâu dài: in 1 lần, dán bàn.
 * tableId: chỉ hiện một bàn; bỏ trống = hiện tất cả các bàn.
 */
export default function TableQRGrid({ tableId = null, onShowAll }) {
  const [baseUrl, setBaseUrl] = useState(import.meta.env.VITE_PUBLIC_URL || window.location.origin);
  const [draftBase, setDraftBase] = useState(baseUrl);
  const [codes, setCodes] = useState(null);       // null = đang tải
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/tables/qr-codes/?base_url=${encodeURIComponent(baseUrl)}`)
      .then(data => { if (active) { setCodes(data); setError(''); } })
      .catch(e => { if (active) { setError(e.message); setCodes([]); } });
    return () => { active = false; };
  }, [baseUrl]);

  async function copy(code) {
    try { await navigator.clipboard.writeText(code.url); setCopied(code.id); setTimeout(() => setCopied(null), 1500); }
    catch { setError('Không sao chép được link — hãy chép thủ công.'); }
  }

  const shown = useMemo(() => (codes || []).filter(c => !tableId || c.table_id === Number(tableId)), [codes, tableId]);
  const picked = shown.filter(c => selected.has(c.id));
  const target = picked.length ? picked : shown;                // không chọn bàn nào = tất cả
  const idsQuery = `base_url=${encodeURIComponent(baseUrl)}${picked.length ? `&ids=${picked.map(c => c.id).join(',')}` : ''}`;
  const defaultBase = shown[0]?.default_base_url;
  const baseDiffers = Boolean(defaultBase) && defaultBase.replace(/\/$/, '') !== baseUrl.replace(/\/$/, '');

  function toggle(id) {
    setSelected(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function download(key, path, name) {
    setBusy(key); setError('');
    try { await saveFile(path, name); } catch (e) { setError(e.message); }
    setBusy('');
  }

  return <div className={styles.wrap}>
    <form className={`${styles.baseForm} ${styles.noPrint}`} onSubmit={e => { e.preventDefault(); setBaseUrl(draftBase.trim().replace(/\/$/, '')); }}>
      <div className="field">
        <label htmlFor="qrgrid-base">Địa chỉ website của nhà hàng (dùng để tạo link trong mã QR)</label>
        <input id="qrgrid-base" className="input" value={draftBase} onChange={e => setDraftBase(e.target.value)} placeholder="https://ten-ban.vercel.app" />
      </div>
      <button type="submit" className="btn btn-secondary">Cập nhật</button>
    </form>
    <p className={`${styles.note} ${styles.noPrint}`}>Mã QR in ra dùng được lâu dài, chỉ cần in và dán một lần. QR phụ thuộc địa chỉ website ở trên: hãy dùng tên miền hoặc IP LAN cố định; nếu đổi địa chỉ hoặc bấm "Đổi mã QR" thì phải in lại.</p>
    {baseDiffers && <div className={`alert alert-warn ${styles.noPrint}`} role="alert">Địa chỉ đang chọn ({baseUrl}) khác địa chỉ cấu hình của máy chủ ({defaultBase}). Chỉ in QR nếu đây đúng là địa chỉ khách sẽ truy cập.</div>}
    {error && <div className={`alert alert-danger ${styles.noPrint}`} role="alert">{error}</div>}
    <div className={`${styles.toolbar} ${styles.noPrint}`} role="toolbar" aria-label="In và tải mã QR">
      <span className={styles.count}>{picked.length ? `Đã chọn ${picked.length}/${shown.length} bàn` : `Tất cả ${shown.length} bàn`}</span>
      {shown.length > 1 && <>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(new Set(shown.map(c => c.id)))}>Chọn tất cả</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(new Set())} disabled={!picked.length}>Bỏ chọn</button>
      </>}
      <span className={styles.spacer} />
      <button type="button" className="btn btn-primary" onClick={() => window.print()} disabled={!target.length}>{picked.length ? 'In bàn đã chọn' : 'In tất cả'}</button>
      <button type="button" className="btn btn-secondary" disabled={!target.length || busy === 'pdf'} onClick={() => download('pdf', `/tables/qr-pdf/?${idsQuery}`, 'the-ban-abc-restaurant.pdf')}>{busy === 'pdf' ? 'Đang tạo…' : 'Tải PDF A4'}</button>
      <button type="button" className="btn btn-secondary" disabled={!target.length || busy === 'zip'} onClick={() => download('zip', `/tables/qr-zip/?${idsQuery}`, 'the-ban-abc-restaurant.zip')}>{busy === 'zip' ? 'Đang tạo…' : 'Tải tất cả (zip)'}</button>
      {tableId && onShowAll && <button type="button" className="btn btn-ghost" onClick={onShowAll}>Xem tất cả bàn</button>}
    </div>
    {codes === null && <div className={styles.grid} aria-hidden="true">{[0, 1, 2, 3].map(i => <div key={i} className={`${styles.card} ${styles.skelCard}`}><span className="skeleton" style={{ width: 80, height: 14 }} /><span className="skeleton" style={{ width: 176, height: 176 }} /><span className="skeleton" style={{ width: 120, height: 14 }} /></div>)}</div>}
    <div className={styles.grid}>
      {shown.map(code => <article className={`${styles.card} ${picked.length && !selected.has(code.id) ? styles.printHide : ''} ${selected.has(code.id) ? styles.picked : ''}`} key={code.id}>
        <label className={`${styles.pick} ${styles.noPrint}`}>
          <input type="checkbox" checked={selected.has(code.id)} onChange={() => toggle(code.id)} aria-label={`Chọn bàn ${code.table_id} để in`} />
        </label>
        <span className={styles.eyebrow}>ABC Restaurant</span>
        <span className={styles.rule} aria-hidden="true" />
        <h2>Bàn {code.table_id}</h2>
        <img src={code.qr_image} alt={`Mã QR bàn ${code.table_id}`} />
        <p className={styles.guide}>Quét để xem thực đơn và gọi món</p>
        <small className={styles.noPrint}>{code.area || 'Nhà hàng'}</small>
        <a className={`${styles.url} ${styles.noPrint}`} href={code.url} target="_blank" rel="noreferrer">{code.url}</a>
        <div className={`${styles.actions} ${styles.noPrint}`}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => copy(code)}>{copied === code.id ? 'Đã chép' : 'Chép link'}</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy === `png${code.id}`} onClick={() => download(`png${code.id}`, `/tables/${code.id}/qr-png/?card=1&base_url=${encodeURIComponent(baseUrl)}`, `the-ban-${code.id}.png`)}>Tải PNG</button>
        </div>
      </article>)}
    </div>
    {codes && !shown.length && !error && <div className="empty"><span className="material-symbols-outlined empty-icon" aria-hidden="true">qr_code_2</span><p className="empty-title">{tableId ? 'Không tìm thấy bàn này' : 'Chưa có bàn nào'}</p>{!tableId && <p>Thêm bàn ở mục "Quản lý Bàn & QR Code".</p>}</div>}
  </div>;
}
