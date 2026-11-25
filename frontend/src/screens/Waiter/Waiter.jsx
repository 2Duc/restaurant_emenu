import { useCallback, useEffect, useState } from 'react';
import { api, money, logout, connectSocket, getRole } from '../../services/api';
import WaiterAddItems from '../../components/WaiterAddItems/WaiterAddItems';
import TableQRGrid from '../../components/TableQRGrid/TableQRGrid';
import ReauthModal from '../../components/ReauthModal/ReauthModal';
import ChangePasswordModal from '../../components/ChangePasswordModal/ChangePasswordModal';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import MaterialIcon from '../../shared/MaterialIcon';
import styles from './styles.module.css';

const TABLE_STATUS={empty:'Trống',occupied:'Đang dùng',cleaning:'Chờ dọn'};
const TABLE_BADGE={empty:'badge-ok',occupied:'badge-brand',cleaning:'badge-warn'};
const ITEM_STATUS={pending:'Chờ bếp',cooking:'Đang nấu',done:'Sẵn sàng',served:'Đã phục vụ'};
const ITEM_BADGE={pending:'badge-neutral',cooking:'badge-warn',done:'badge-ok',served:'badge-info'};
const hhmm=v=>v?new Date(v).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}):'';

export default function Waiter() {
  const [confirm, confirmDialog] = useConfirm();
  const [tables,setTables]=useState([]); const [orders,setOrders]=useState([]); const [calls,setCalls]=useState([]);
  const [qrFor,setQrFor]=useState(null); /* null = đóng, 'all' = mọi bàn, hoặc object bàn */ const [addFor,setAddFor]=useState(null); const [reauth,setReauth]=useState(false); const [pwOpen,setPwOpen]=useState(false);
  const [selected,setSelected]=useState(null); const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  const refresh=useCallback(async()=>{try{const [t,o,c]=await Promise.all([api.get('/tables/'),api.get('/orders/?active=1'),api.get('/staff-calls/?status=pending')]);setTables(t.results||t);setOrders(o.results||o);setCalls(c.results||c);}catch(e){setError(e.message);}},[]);
  useEffect(()=>{const first=setTimeout(refresh,0);const timer=setInterval(refresh,12000);const close=connectSocket('staff_orders',{onMessage:()=>refresh()});return()=>{clearTimeout(first);clearInterval(timer);close();};},[refresh]);
  async function updateItem(item,status){setBusy(true);setError('');try{await api.patch(`/order-items/${item.id}/status/`,{status});await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function cancelItem(item){if(!await confirm(`Huỷ món "${item.menu_item_name}"?`,{danger:true,confirmLabel:'Huỷ món'}))return;setBusy(true);setError('');try{await api.post(`/order-items/${item.id}/cancel/`,{});await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function handleCall(call,status){setBusy(true);try{await api.patch(`/staff-calls/${call.id}/status/`,{status});await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function setTableStatus(table,status){setBusy(true);try{await api.patch(`/tables/${table.id}/status/`,{status});await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function cashPayment(order){const bank=order.payment_method==='bank_transfer'&&order.payment_status==='pending'&&order.payment_id;if(!await confirm(bank?`Xác nhận đã nhận ${money(order.total_amount)} chuyển khoản cho đơn #${order.id}?`:`Xác nhận đã thu ${money(order.total_amount)} cho đơn #${order.id}?`))return;setBusy(true);try{const pay=bank||(order.payment_method==='cash'&&order.payment_status==='pending'&&order.payment_id)?{id:order.payment_id,status:'pending'}:await api.post('/payments/create/',{order_id:order.id,method:'cash'});if(pay.status!=='success')await api.post(`/payments/${pay.id}/confirm-manual/`);await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  const activeOrders=orders.filter(o=>!['completed','cancelled'].includes(o.status));
  const sortedCalls=[...calls].sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)));
  const seatedAt=t=>{const os=activeOrders.filter(o=>o.table===t.id||o.table_number===t.number).map(o=>o.created_at).filter(Boolean).sort();return os[0];};
  const isCashWait=o=>['cash','bank_transfer'].includes(o.payment_method)&&o.payment_status==='pending';
  const cashCount=activeOrders.filter(isCashWait).length;
  return <div className={styles.page}>
    {confirmDialog}
    <header className={styles.header}>
      <div className={styles.brand}><span className={styles.mono} aria-hidden="true">ABC</span><b>ABC Restaurant</b><span className={styles.role}>Phục vụ</span></div>
      <div className={styles.headerRight}>
        <span className={styles.live}><i aria-hidden="true"/>Trực tiếp</span>
        {['QL','AD'].includes(getRole())&&<button className={`btn btn-sm ${styles.hbtn}`} onClick={()=>setReauth(true)}><MaterialIcon name="undo" size={18}/><span className={styles.hideSm}>Về chế độ Quản lý</span></button>}
        <button className={`btn btn-sm ${styles.hbtn}`} onClick={()=>setPwOpen(true)}><MaterialIcon name="key" size={18}/><span className={styles.hideSm}>Đổi mật khẩu</span></button>
        <button className={`btn btn-sm ${styles.hbtn}`} onClick={refresh} aria-label="Làm mới"><MaterialIcon name="refresh" size={18}/><span className={styles.hideSm}>Làm mới</span></button>
        <button className={`btn btn-sm ${styles.hbtn}`} onClick={()=>{logout();location.href='/login';}}><MaterialIcon name="logout" size={18}/><span className={styles.hideSm}>Đăng xuất</span></button>
      </div>
    </header>
    <main className={styles.main}>
      <div className={styles.heading}>
        <div><span className={styles.kicker}>Ca phục vụ</span><h1>Sơ đồ bàn</h1></div>
        <div className={styles.headLinks}>
          <button className="btn btn-secondary" onClick={()=>setQrFor('all')}><MaterialIcon name="qr_code_2" size={20}/>Mã QR các bàn</button>
          <a className="btn btn-secondary" href={`/table/${tables[0]?.id||1}`} target="_blank" rel="noreferrer"><MaterialIcon name="open_in_new" size={20}/>Menu khách</a>
        </div>
      </div>
      {error&&<div className="alert alert-danger" role="alert">{error}</div>}
      <dl className={styles.stats}>
        <div><dt>Tổng số bàn</dt><dd className="num">{tables.length}</dd></div>
        <div><dt>Đang dùng</dt><dd className="num">{tables.filter(t=>t.status==='occupied').length}</dd></div>
        <div><dt>Đơn đang mở</dt><dd className="num">{activeOrders.length}</dd></div>
        <div className={calls.length?styles.statWarn:''}><dt>Khách gọi</dt><dd className="num">{calls.length}</dd></div>
      </dl>
      {sortedCalls.length>0&&<section className={styles.calls} aria-label="Yêu cầu gọi phục vụ">
        <h2 className={styles.sectionTitle}><MaterialIcon name="notifications_active" size={20}/>Khách đang gọi <span className="badge badge-warn num">{sortedCalls.length}</span></h2>
        <ul className={styles.callList}>{sortedCalls.map((c,idx)=><li className={`${styles.call} ${idx===0?styles.callNew:''}`} key={c.id}>
          <div className={styles.callTable}><small>Bàn</small><b className="num">{c.table_number}</b></div>
          <div className={styles.callBody}><p>{c.message||'Khách cần hỗ trợ'}</p><span className="num">{hhmm(c.created_at)}{idx===0?' · mới nhất':''}</span></div>
          <div className={styles.callActions}>
            <button className="btn btn-secondary" onClick={()=>handleCall(c,'accepted')} disabled={busy}>Nhận xử lý</button>
            <button className="btn btn-primary" onClick={()=>handleCall(c,'resolved')} disabled={busy}>Đã xong</button>
          </div>
        </li>)}</ul>
      </section>}
      <div className={styles.columns}>
        <section className={styles.tablesPane} aria-label="Sơ đồ bàn">
          <div className={styles.paneHead}>
            <h2 className={styles.sectionTitle}><MaterialIcon name="table_restaurant" size={20}/>Bàn</h2>
            <div className={styles.legend}><span><i className={styles.dotEmpty}/>Trống</span><span><i className={styles.dotOcc}/>Đang dùng</span><span><i className={styles.dotClean}/>Chờ dọn</span></div>
          </div>
          {tables.length?<div className={styles.tableGrid}>{tables.map(t=>{const at=seatedAt(t);return <button key={t.id} onClick={()=>setSelected(t)} className={`${styles.tableCard} ${styles[t.status]||''}`} aria-label={`Bàn ${t.number}, ${TABLE_STATUS[t.status]||''}`}>
            <span className={styles.tableTop}><b className={`${styles.tableNo} num`}>{t.number}</b><span className={`badge ${TABLE_BADGE[t.status]||''}`}>{TABLE_STATUS[t.status]}</span></span>
            <span className={styles.tableMeta}>{t.area||'Nhà hàng'} · {t.capacity} chỗ</span>
            <span className={`${styles.tableTime} num`}>{t.status==='occupied'&&at?`Vào bàn ${hhmm(at)}`:' '}</span>
          </button>;})}</div>
          :<div className="empty"><MaterialIcon name="table_restaurant" className="empty-icon"/><p className="empty-title">Chưa có bàn nào</p><p>Quản lý thêm bàn ở mục Quản lý bàn.</p></div>}
        </section>
        <aside className={styles.side} aria-label="Đơn đang phục vụ">
          <div className={styles.paneHead}><h2 className={styles.sectionTitle}><MaterialIcon name="receipt_long" size={20}/>Đơn đang mở <span className="badge badge-neutral num">{activeOrders.length}</span></h2>{cashCount>0&&<span className="badge badge-warn">{cashCount} chờ thu tiền</span>}</div>
          {activeOrders.length?activeOrders.map(o=>{const cash=isCashWait(o);return <article className={`${styles.order} ${cash?styles.orderCash:''}`} key={o.id}>
            {cash&&<p className={styles.cashWait}><MaterialIcon name={o.payment_method==='bank_transfer'?'account_balance':'payments'} size={20}/>{o.payment_method==='bank_transfer'?'Khách đang chờ xác nhận chuyển khoản':'Khách đang chờ thanh toán tiền mặt'}</p>}
            <div className={styles.orderHead}><div><b className={styles.orderTable}>Bàn {o.table_number}</b><span className={`${styles.orderId} num`}>Đơn #{o.id} · {hhmm(o.created_at)}</span></div><strong className="num">{money(o.total_amount)}</strong></div>
            <ul className={styles.items}>{o.items?.map(i=><li className={styles.item} key={i.id}>
              <span className={`${styles.qty} num`}>{i.quantity}×</span>
              <div className={styles.itemBody}><b>{i.menu_item_name}</b>{i.note&&<span className={styles.note}>{i.note}</span>}</div>
              <span className={`badge ${ITEM_BADGE[i.status]||''}`}>{ITEM_STATUS[i.status]}</span>
              {i.status==='done'&&<button className="btn btn-primary btn-sm" disabled={busy} onClick={()=>updateItem(i,'served')}>Đã bưng</button>}
              {i.status==='pending'&&<button className={`btn btn-sm ${styles.hbtn}`} disabled={busy} onClick={()=>cancelItem(i)}>Huỷ món</button>}
            </li>)}</ul>
            <button className={`btn btn-block ${cash?'btn-primary btn-lg':'btn-secondary'}`} disabled={busy||(o.items?.some(i=>i.status!=='served')&&!cash)} onClick={()=>cashPayment(o)}>{o.payment_method==='bank_transfer'&&cash?'Xác nhận đã nhận chuyển khoản':'Xác nhận thu tiền mặt'}</button>
          </article>}):<div className="empty"><MaterialIcon name="receipt_long" className="empty-icon"/><p className="empty-title">Không có đơn đang mở</p><p>Đơn mới của khách sẽ hiện ở đây.</p></div>}
        </aside>
      </div>
    </main>
    {qrFor&&<div className="modal-backdrop" onClick={e=>e.target===e.currentTarget&&setQrFor(null)}><section className={`modal ${styles.qrDialog}`} role="dialog" aria-modal="true" aria-label="Mã QR bàn"><div className="modal-head"><div><span className="modal-eyebrow">Mã QR bàn</span><h2 className="modal-title">{qrFor==='all'?'Mã QR các bàn':`Bàn ${qrFor.id}`}</h2></div><button className="modal-close" onClick={()=>setQrFor(null)} aria-label="Đóng"><MaterialIcon name="close" size={20}/></button></div><TableQRGrid tableId={qrFor==='all'?null:qrFor.id} onShowAll={()=>setQrFor('all')} /></section></div>}
    {addFor&&<WaiterAddItems table={addFor} onClose={()=>setAddFor(null)} onDone={async()=>{setAddFor(null);await refresh();}} />}
    {reauth&&<ReauthModal onClose={()=>setReauth(false)} onSuccess={async()=>{try{await api.post('/audit-logs/',{action:'SWITCH_MODE',mode:'manager',reason:'Quay lại quản lý (đã nhập lại mật khẩu)'});}catch{/* vẫn quay lại */}location.href='/manager';}} />}
    {pwOpen&&<ChangePasswordModal onClose={()=>setPwOpen(false)} />}
    {selected&&<div className="modal-backdrop" onClick={e=>e.target===e.currentTarget&&setSelected(null)}><section className="modal modal-sm" role="dialog" aria-modal="true" aria-label={`Bàn ${selected.number}`}>
      <div className="modal-head"><div><span className="modal-eyebrow">Chi tiết bàn</span><h2 className="modal-title">Bàn {selected.number}</h2></div><button className="modal-close" onClick={()=>setSelected(null)} aria-label="Đóng"><MaterialIcon name="close" size={20}/></button></div>
      <dl className={styles.facts}><div><dt>Khu vực</dt><dd>{selected.area||'Nhà hàng'}</dd></div><div><dt>Sức chứa</dt><dd className="num">{selected.capacity} khách</dd></div><div><dt>Trạng thái</dt><dd><span className={`badge ${TABLE_BADGE[selected.status]||''}`}>{TABLE_STATUS[selected.status]}</span></dd></div></dl>
      <div className={styles.dialogActions}>
        {selected.status==='cleaning'&&<button className="btn btn-primary btn-lg btn-block" onClick={()=>{setTableStatus(selected,'empty');setSelected(null);}}>Xác nhận đã dọn xong</button>}
        {selected.status!=='cleaning'&&<button className="btn btn-primary btn-lg btn-block" onClick={()=>{setAddFor(selected);setSelected(null);}}>Gọi món hộ khách</button>}
        <button className="btn btn-secondary btn-lg btn-block" onClick={()=>{setQrFor(selected);setSelected(null);}}>Xem mã QR bàn</button>
      </div>
    </section></div>}
  </div>;
}
