import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, money } from '../../services/api';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import SkeletonRows from '../../shared/SkeletonRows';

const EMPTY = { id: null, name: '', price: '', category: '', description: '', is_available: true, image: null, preview: '' };
const mediaBase = import.meta.env.VITE_MEDIA_BASE_URL || 'http://127.0.0.1:8000';
const imgSrc = u => !u ? '' : u.startsWith('http') ? u : `${mediaBase}${u}`;

export default function ManagerMenu() {
  const [confirm, confirmDialog] = useConfirm();
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [cats, setCats] = useState([]);
  const [filterCat, setFilterCat] = useState('all');
  const [search, setSearch] = useState('');
  const [form, setForm] = useState(null);       // món đang thêm/sửa
  const [catForm, setCatForm] = useState(null); // danh mục đang thêm/sửa
  const [msg, setMsg] = useState({ type: '', text: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, c] = await Promise.all([api.get('/menu-items/?ordering=name'), api.get('/categories/')]);
      setItems(m.results || m); setCats(c.results || c);
    } catch (e) { setMsg({ type: 'error', text: e.message }); }
    setLoaded(true);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => items.filter(i => (filterCat === 'all' || String(i.category) === filterCat) && i.name.toLowerCase().includes(search.toLowerCase())), [items, filterCat, search]);
  const flash = (type, text) => setMsg({ type, text });

  async function saveItem(e) {
    e.preventDefault(); setBusy(true);
    try {
      const body = new FormData();
      body.append('name', form.name.trim()); body.append('price', String(Number(form.price)));
      body.append('description', form.description); body.append('is_available', String(form.is_available));
      body.append('category', form.category || '');
      if (form.image) body.append('image_url', form.image);
      if (form.id) await api.patchForm(`/menu-items/${form.id}/`, body); else await api.upload('/menu-items/', body);
      setForm(null); flash('success', form.id ? 'Đã cập nhật món.' : 'Đã thêm món.'); await load();
    } catch (err) { flash('error', err.message); } finally { setBusy(false); }
  }
  async function toggle(item) {
    try { await api.patch(`/menu-items/${item.id}/`, { is_available: !item.is_available }); await load(); } catch (err) { flash('error', err.message); }
  }
  async function removeItem(item) {
    if (!await confirm(`Xoá món "${item.name}"?`, { danger: true, confirmLabel: 'Xoá' })) return;
    try { await api.delete(`/menu-items/${item.id}/`); flash('success', 'Đã xoá món.'); await load(); } catch (err) { flash('error', err.message); }
  }
  async function saveCat(e) {
    e.preventDefault();
    try {
      const body = { name: catForm.name.trim(), description: catForm.description || '', sort_order: Number(catForm.sort_order || 0) };
      if (catForm.id) await api.patch(`/categories/${catForm.id}/`, body); else await api.post('/categories/', body);
      setCatForm(null); flash('success', 'Đã lưu danh mục.'); await load();
    } catch (err) { flash('error', err.message); }
  }
  async function removeCat(cat) {
    if (!await confirm(`Xoá danh mục "${cat.name}"?`, { danger: true, confirmLabel: 'Xoá' })) return;
    try { await api.delete(`/categories/${cat.id}/`); flash('success', 'Đã xoá danh mục.'); if (filterCat === String(cat.id)) setFilterCat('all'); await load(); } catch (err) { flash('error', err.message); }
  }

  return <div className={ui.panel}>
    {confirmDialog}
    <div className={ui.head}>
      <p className={ui.lead}>{items.length} món · {cats.length} danh mục</p>
      <button className="btn btn-primary" onClick={() => setForm({ ...EMPTY, category: filterCat !== 'all' ? filterCat : '' })}><MaterialIcon name="add" size={18} />Thêm món</button>
    </div>
    {msg.text && <div className={`alert ${msg.type === 'error' ? 'alert-danger' : 'alert-ok'}`} role="status">{msg.text}</div>}

    <div className="card"><h3 className={ui.sectionTitle}>Danh mục</h3>
      <div className={ui.cats}>
        {cats.map(c => <span key={c.id} className={ui.cat}><span>{c.name}</span>
          <button onClick={() => setCatForm({ ...c })} aria-label={`Sửa ${c.name}`}><MaterialIcon name="edit" size={16} /></button>
          <button onClick={() => removeCat(c)} aria-label={`Xoá ${c.name}`}><MaterialIcon name="close" size={16} /></button></span>)}
        <button className="btn btn-secondary btn-sm" onClick={() => setCatForm({ id: null, name: '', description: '', sort_order: cats.length + 1 })}><MaterialIcon name="add" size={16} />Thêm danh mục</button>
      </div>
    </div>

    <div className={ui.toolbar}>
      <label className="field" style={{ flex: '1 1 240px', maxWidth: 360 }}><span className="field-label">Tìm món</span><input className="input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tên món" /></label>
      <label className="field"><span className="field-label">Danh mục</span><select className="select" value={filterCat} onChange={e => setFilterCat(e.target.value)}><option value="all">Tất cả</option>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    </div>
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Ảnh</th><th>Tên món</th><th>Danh mục</th><th className="num">Giá</th><th>Trạng thái</th><th /></tr></thead>
      <tbody>{shown.map(i => <tr key={i.id}>
        <td>{i.image_url ? <img className={ui.thumb} src={imgSrc(i.image_url)} alt="" /> : <span className={ui.thumb}><MaterialIcon name="restaurant" size={20} /></span>}</td>
        <td><div className={ui.dishName}>{i.name}</div><div className={ui.desc}>{i.description}</div></td>
        <td>{i.category_name || '—'}</td><td className="num">{money(i.price)}</td>
        <td><button className={`badge ${i.is_available ? 'badge-ok' : 'badge-neutral'} ${ui.statusToggle}`} title="Bấm để đổi trạng thái" onClick={() => toggle(i)}>{i.is_available ? 'Đang bán' : 'Ngừng bán'}</button></td>
        <td><div className={ui.rowActions}><button className="btn btn-secondary btn-sm" onClick={() => setForm({ ...EMPTY, ...i, category: i.category ?? '', price: String(Number(i.price)), image: null, preview: imgSrc(i.image_url) })}>Sửa</button><button className="btn btn-ghost btn-sm" onClick={() => removeItem(i)}>Xoá</button></div></td>
      </tr>)}</tbody>
    </table>{!loaded ? <SkeletonRows /> : !shown.length && <div className="empty"><MaterialIcon name="restaurant_menu" size={32} className="empty-icon" /><p>{items.length ? 'Không có món nào khớp bộ lọc.' : 'Chưa có món nào. Bấm “Thêm món” để tạo món đầu tiên.'}</p></div>}</div>

    {form && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setForm(null)}><form className="modal" onSubmit={saveItem}>
      <div className="modal-head"><h3 className="modal-title">{form.id ? 'Sửa món ăn' : 'Thêm món ăn'}</h3><button type="button" className="modal-close" aria-label="Đóng" onClick={() => setForm(null)}><MaterialIcon name="close" size={20} /></button></div>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Tên món</span><input className="input" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
        <label className="field"><span className="field-label">Giá (VND)</span><input className="input" required type="number" min="1000" step="1000" value={form.price} onChange={e => setForm({ ...form, price: e.target.value })} /></label>
        <label className="field"><span className="field-label">Danh mục</span><select className="select" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}><option value="">Chưa phân loại</option>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="field"><span className="field-label">Ảnh món</span><input className="input" type="file" accept="image/*" onChange={e => { const f = e.target.files?.[0] || null; setForm({ ...form, image: f, preview: f ? URL.createObjectURL(f) : form.preview }); }} /></label>
      </div>
      <label className="field"><span className="field-label">Mô tả</span><textarea className="textarea" rows={3} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
      {form.preview && <img className={ui.preview} src={form.preview} alt="Xem trước" />}
      <label className={ui.check}><input type="checkbox" checked={form.is_available} onChange={e => setForm({ ...form, is_available: e.target.checked })} /> Đang bán</label>
      <div className="modal-foot"><button type="button" className="btn btn-secondary" onClick={() => setForm(null)}>Huỷ</button><button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? 'Đang lưu…' : 'Lưu món'}</button></div>
    </form></div>}

    {catForm && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setCatForm(null)}><form className="modal" onSubmit={saveCat}>
      <div className="modal-head"><h3 className="modal-title">{catForm.id ? 'Sửa danh mục' : 'Thêm danh mục'}</h3><button type="button" className="modal-close" aria-label="Đóng" onClick={() => setCatForm(null)}><MaterialIcon name="close" size={20} /></button></div>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Tên danh mục</span><input className="input" required value={catForm.name} onChange={e => setCatForm({ ...catForm, name: e.target.value })} /></label>
        <label className="field"><span className="field-label">Thứ tự hiển thị</span><input className="input" type="number" min="0" value={catForm.sort_order} onChange={e => setCatForm({ ...catForm, sort_order: e.target.value })} /></label>
      </div>
      <label className="field"><span className="field-label">Mô tả</span><input className="input" value={catForm.description || ''} onChange={e => setCatForm({ ...catForm, description: e.target.value })} /></label>
      <div className="modal-foot"><button type="button" className="btn btn-secondary" onClick={() => setCatForm(null)}>Huỷ</button><button className="btn btn-primary">Lưu danh mục</button></div>
    </form></div>}
  </div>;
}
