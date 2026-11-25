import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import MaterialIcon from '../../shared/MaterialIcon';
import ui from '../Manager/styles.module.css';
import styles from './styles.module.css';

const BANKS = [
  ['970436', 'Vietcombank'], ['970415', 'VietinBank'], ['970418', 'BIDV'], ['970405', 'Agribank'],
  ['970407', 'Techcombank'], ['970422', 'MB Bank'], ['970416', 'ACB'], ['970432', 'VPBank'],
  ['970423', 'TPBank'], ['970403', 'Sacombank'], ['970441', 'VIB'], ['970437', 'HDBank'],
];
const METHODS = [
  ['cash_enabled', 'Tiền mặt', 'Khách trả trực tiếp, nhân viên xác nhận.'],
  ['bank_transfer_enabled', 'Chuyển khoản ngân hàng', 'Mã VietQR + nhân viên xác nhận đã nhận tiền. Cần nhập tài khoản nhận bên dưới.'],
  ['vnpay_enabled', 'VNPay', 'Thanh toán qua cổng VNPay (tự động đối soát).'],
];
const GATEWAY_MODE = { vnpay: 'VNPay (thật / sandbox)', mock: 'Giả lập (demo)' };

export default function ManagerSettings() {
  const [form, setForm] = useState(null);
  const [gateway, setGateway] = useState(null);
  const [msg, setMsg] = useState({ type: '', text: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.get('/settings/');
      setForm(d.config); setGateway(d.gateway);
    } catch (e) { setMsg({ type: 'error', text: e.message }); }
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  function pickBank(bin) {
    const hit = BANKS.find(b => b[0] === bin);
    setForm(f => ({ ...f, bank_bin: bin, bank_name: hit ? hit[1] : f.bank_name }));
  }

  async function save(e) {
    e.preventDefault(); setSaving(true); setMsg({ type: '', text: '' });
    try {
      const body = { ...form, staff_call_cooldown_minutes: Number(form.staff_call_cooldown_minutes) };
      delete body.updated_at;
      const d = await api.patch('/settings/', body);
      setForm(d.config); setGateway(d.gateway);
      setMsg({ type: 'success', text: 'Đã lưu cấu hình.' });
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
    setSaving(false);
  }

  if (!form) return <div className={ui.panel}>{msg.text ? <div className="alert alert-danger" role="alert">{msg.text}</div> : <div className={`skeleton ${styles.skel}`} aria-hidden="true" />}</div>;
  const bankReady = form.bank_bin && form.bank_account_no && form.bank_account_name;

  return <form className={ui.panel} onSubmit={save}>
    <div className={ui.head}><p className={ui.lead}>Bật / tắt phương thức thanh toán, tài khoản nhận chuyển khoản và các thông số vận hành. Chỉ Quản trị viên được thay đổi.</p>
      <button className="btn btn-primary" type="submit" disabled={saving}><MaterialIcon name="save" size={18} />{saving ? 'Đang lưu…' : 'Lưu cấu hình'}</button></div>
    {msg.text && <div className={`alert ${msg.type === 'error' ? 'alert-danger' : 'alert-ok'}`} role={msg.type === 'error' ? 'alert' : 'status'}>{msg.text}</div>}

    <section className={`card ${styles.section}`} aria-labelledby="st-methods">
      <h2 id="st-methods" className={styles.h}><MaterialIcon name="payments" size={20} />Phương thức thanh toán</h2>
      <ul className={styles.methods}>{METHODS.map(([key, label, hint]) => <li key={key}>
        <label className={styles.toggle}>
          <input type="checkbox" checked={!!form[key]} onChange={e => set(key, e.target.checked)} />
          <span><b>{label}</b><small>{hint}</small></span>
        </label>
        {key === 'bank_transfer_enabled' && form[key] && !bankReady && <span className="badge badge-warn">Chưa cấu hình tài khoản — khách sẽ không thấy lựa chọn này</span>}
      </li>)}</ul>
    </section>

    <section className={`card ${styles.section}`} aria-labelledby="st-bank">
      <h2 id="st-bank" className={styles.h}><MaterialIcon name="account_balance" size={20} />Tài khoản nhận chuyển khoản</h2>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Ngân hàng</span>
          <select className="select" value={BANKS.some(b => b[0] === form.bank_bin) ? form.bank_bin : ''} onChange={e => pickBank(e.target.value)}>
            <option value="">— Chọn ngân hàng —</option>{BANKS.map(([bin, name]) => <option key={bin} value={bin}>{name}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Mã BIN (6 chữ số)</span><input className="input" inputMode="numeric" maxLength={6} value={form.bank_bin} onChange={e => set('bank_bin', e.target.value.replace(/\D/g, ''))} /></label>
        <label className="field"><span className="field-label">Tên ngân hàng</span><input className="input" maxLength={100} value={form.bank_name} onChange={e => set('bank_name', e.target.value)} /></label>
        <label className="field"><span className="field-label">Số tài khoản</span><input className="input" inputMode="numeric" maxLength={19} value={form.bank_account_no} onChange={e => set('bank_account_no', e.target.value.replace(/\D/g, ''))} /></label>
        <label className="field"><span className="field-label">Chủ tài khoản</span><input className="input" maxLength={100} value={form.bank_account_name} onChange={e => set('bank_account_name', e.target.value)} /><span className="field-hint">Viết hoa, không dấu giống tên trên ngân hàng.</span></label>
      </div>
    </section>

    <section className={`card ${styles.section}`} aria-labelledby="st-ops">
      <h2 id="st-ops" className={styles.h}><MaterialIcon name="tune" size={20} />Vận hành</h2>
      <div className={ui.formGrid}>
        <label className="field"><span className="field-label">Chống spam gọi nhân viên (phút)</span><input className="input" type="number" min={1} max={30} value={form.staff_call_cooldown_minutes} onChange={e => set('staff_call_cooldown_minutes', e.target.value)} /><span className="field-hint">Khách gọi lại trong khoảng này sẽ dùng lại yêu cầu đang chờ.</span></label>
        <label className="field"><span className="field-label">Ghi chú hoá đơn</span><input className="input" maxLength={255} value={form.invoice_note} onChange={e => set('invoice_note', e.target.value)} /><span className="field-hint">Hiện ở cuối hoá đơn của khách.</span></label>
      </div>
    </section>

    <section className={`card ${styles.section}`} aria-labelledby="st-gw">
      <h2 id="st-gw" className={styles.h}><MaterialIcon name="lock" size={20} />Cổng thanh toán (chỉ đọc, cấu hình bằng biến môi trường)</h2>
      <dl className={styles.facts}>
        <div><dt>Chế độ</dt><dd><span className="badge badge-brand">{GATEWAY_MODE[gateway?.mode] || gateway?.mode}</span></dd></div>
        <div><dt>Mã TMN</dt><dd className="num">{gateway?.tmn_code || '—'}</dd></div>
        <div><dt>Khoá bí mật</dt><dd><span className={`badge ${gateway?.has_hash_secret ? 'badge-ok' : 'badge-neutral'}`}>{gateway?.has_hash_secret ? 'Đã cấu hình' : 'Chưa có'}</span></dd></div>
      </dl>
    </section>
  </form>;
}
