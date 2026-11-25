import { useState } from 'react';
import MaterialIcon from '../../shared/MaterialIcon';

/** Hộp thoại xác nhận (thay window.confirm). */
export function ConfirmDialog({ message, confirmLabel = 'Xác nhận', cancelLabel = 'Huỷ bỏ', danger = false, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onCancel()} onKeyDown={e => e.key === 'Escape' && onCancel()}>
      <section className="modal modal-sm" role="alertdialog" aria-modal="true" aria-label="Xác nhận">
        <div className="modal-head"><h2 className="modal-title">Xác nhận</h2><button type="button" className="modal-close" onClick={onCancel} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button></div>
        <p>{message}</p>
        <div className="modal-foot">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} autoFocus onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}

/**
 * Hộp thoại nhập liệu (thay window.prompt). fields: [{name, label, type, value, min, max}].
 * onSubmit(values) được gọi khi bấm Lưu.
 */
export function PromptDialog({ title, fields, submitLabel = 'Lưu', onSubmit, onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map(f => [f.name, f.value ?? ''])));
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onCancel()} onKeyDown={e => e.key === 'Escape' && onCancel()}>
      <form className="modal modal-sm" role="dialog" aria-modal="true" aria-label={title} onSubmit={e => { e.preventDefault(); onSubmit(values); }}>
        <div className="modal-head"><h2 className="modal-title">{title}</h2><button type="button" className="modal-close" onClick={onCancel} aria-label="Đóng"><MaterialIcon name="close" size={20} /></button></div>
        {fields.map((f, i) => <label className="field" key={f.name}><span className="field-label">{f.label}</span>
          <input className="input" type={f.type || 'text'} min={f.min} max={f.max} autoFocus={i === 0} value={values[f.name]} onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))} /></label>)}
        <div className="modal-foot">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>Huỷ bỏ</button>
          <button type="submit" className="btn btn-primary">{submitLabel}</button>
        </div>
      </form>
    </div>
  );
}
