import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, connectSocket, ensureTableAccess, getAccessToken, money as vnd } from '../../services/api';
import PaymentModal from '../../components/PaymentModal/PaymentModal';
import { useConfirm } from '../../components/ConfirmDialog/useConfirm';
import ReviewModal from '../../components/ReviewModal/ReviewModal';
import Toast from '../../shared/Toast';
import BillModal from '../../components/BillModal/BillModal';
import { addToCart, cartCount, cartTotal, changeCartQty, filterMenuItems } from './cartUtils';
import styles from './styles.module.css';

const ITEM_STATUS = { pending: 'Chờ bếp', cooking: 'Đang nấu', done: 'Sẵn sàng', served: 'Đã phục vụ', cancelled: 'Đã huỷ' };
const ITEM_BADGE = { pending: 'badge-neutral', cooking: 'badge-warn', done: 'badge-info', served: 'badge-ok', cancelled: 'badge-danger' };
const STEPS = ['Chờ bếp nhận', 'Đang nấu', 'Đã phục vụ'];
const isOpen = order => order && !['completed', 'cancelled'].includes(order.status);

export default function Menu() {
  // Link QR của bàn có dạng /table/<id>; id của bàn chính là số bàn.
  // /menu?table=<id> vẫn được hỗ trợ cho link cũ.
  const { tableId } = useParams();
  const [params] = useSearchParams();
  const tableKey = tableId || params.get('table') || '1';

  const [table, setTable] = useState(null);
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [activeCategory, setActiveCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [cart, setCart] = useState([]);
  const [note, setNote] = useState('');
  const [promoCode, setPromoCode] = useState('');
  const [showCart, setShowCart] = useState(false);
  const [showService, setShowService] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showBill, setShowBill] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [order, setOrder] = useState(null);
  const [showReview, setShowReview] = useState(false);
  const [toast, setToast] = useState('');
  const [accessError, setAccessError] = useState(false);
  const [confirm, confirmDialog] = useConfirm();

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        // AUTH-05: khách phải mở bằng link QR có mã k (hoặc đã có phiên bàn); nhân viên đăng nhập thì không cần.
        const hasAccess = await ensureTableAccess(tableKey, params.get('k'));
        if (!hasAccess && !getAccessToken()) { if (active) setAccessError(true); return; }
        const t = await api.get(`/tables/${encodeURIComponent(tableKey)}/`);
        const [menu, cats, current] = await Promise.all([
          api.get('/menu-items/?ordering=name'),
          api.get('/categories/'),
          api.get(`/tables/${t.id}/current-order/`).catch(() => null),
        ]);
        if (!active) return;
        setTable(t); setItems(menu.results || menu); setCategories(cats.results || cats);
        setOrder(current);
      } catch (e) {
        if (active) setMessage(`Không tải được dữ liệu: ${e.message}`);
      }
    })();
    return () => { active = false; };
  }, [tableKey, params]);

  useEffect(() => {
    if (!table?.id) return undefined;
    return connectSocket(`table_${table.id}`, { onMessage: e => {
        let data;
        try { data = JSON.parse(e.data); } catch { return; }
        if (data.type === 'item_status_updated' && data.order_item.order) api.get(`/orders/${data.order_item.order}/`).then(setOrder).catch(() => {});
        if (data.type === 'new_order' || data.type === 'order_updated') {
          setOrder(current => (!current || current.id === data.order.id || !isOpen(current) ? data.order : current));
          if (data.type === 'order_updated' && data.order.status === 'completed') setMessage(`Đơn #${data.order.id} đã thanh toán thành công. Cảm ơn quý khách!`);
          if (data.type === 'order_updated' && data.order.status === 'cancelled') setMessage(`Đơn #${data.order.id} đã bị huỷ.`);
        }
        if (data.type === 'staff_call' && data.call.status === 'accepted') setMessage('Nhân viên đang đến bàn của bạn.');
        if (data.type === 'table_updated') setTable(t => ({ ...t, ...data.table }));
    } });
  }, [table?.id]);

  // Bếp báo hết món → menu khách tự cập nhật (BR-04).
  useEffect(() => {
    const timer = setInterval(() => {
      api.get('/menu-items/?ordering=name').then(menu => {
        const list = menu.results || menu;
        setItems(list);
        setCart(current => current.filter(x => list.some(i => i.id === x.id)));
      }).catch(() => {});
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  async function cancelItem(item) {
    if (!await confirm(`Huỷ món "${item.menu_item_name}"?`, { danger: true, confirmLabel: 'Huỷ món' })) return;
    setBusy(true);
    try {
      const updated = await api.post(`/order-items/${item.id}/cancel/`, {});
      setOrder(updated);
      setMessage(updated.status === 'cancelled' ? `Đã huỷ đơn #${updated.id}.` : `Đã huỷ món ${item.menu_item_name}.`);
    } catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }

  const filtered = useMemo(() => filterMenuItems(items, activeCategory, search), [items, activeCategory, search]);
  const count = cartCount(cart);
  const total = cartTotal(cart);
  const add = item => setCart(current => addToCart(current, item));
  const changeQty = (id, delta) => setCart(current => changeCartQty(current, id, delta));

  async function sendCall(text) {
    if (!table?.id) return setMessage('Không xác định được bàn. Vui lòng mở menu từ mã QR của bàn.');
    try {
      await api.post('/staff-calls/', { table: table.id, message: text });
      setShowService(false); setMessage('Đã gửi yêu cầu đến nhân viên phục vụ.');
    } catch (e) { setMessage(e.message); }
  }

  // Đặt món chỉ gửi đơn tới bếp. Thanh toán là bước riêng, bấm nút "Thanh toán" mới hiện.
  async function checkout(event) {
    event.preventDefault();
    if (!table?.id || !cart.length) return;
    setBusy(true); setMessage('');
    try {
      const lines = cart.map(x => ({ menu_item_id: x.id, quantity: x.quantity, note }));
      let activeOrder = isOpen(order)
        ? await api.post(`/orders/${order.id}/add-items/`, { items: lines })
        : await api.post('/orders/', { table_id: table.id, items: lines });
      if (promoCode.trim()) activeOrder = await api.post(`/orders/${activeOrder.id}/apply-promotion/`, { code: promoCode.trim() });
      setOrder(activeOrder);
      setCart([]); setNote(''); setPromoCode(''); setShowCart(false);
      setMessage(`Đã gửi đơn #${activeOrder.id} đến bếp. Bấm "Thanh toán" khi bạn muốn trả tiền.`);
    } catch (e) { setMessage(e.message || 'Không thể tạo đơn hàng.'); }
    finally { setBusy(false); }
  }

  const payable = isOpen(order);
  const displayTable = table?.id ?? tableKey;
  const imageSrc = item => item.image_url.startsWith('http') ? item.image_url : `${import.meta.env.VITE_MEDIA_BASE_URL || 'http://127.0.0.1:8000'}${item.image_url}`;

  const loading = !table && !message;
  const failed = !table && Boolean(message);
  const cartQty = id => cart.find(x => x.id === id)?.quantity || 0;
  const tableLabel = /^\d+$/.test(String(displayTable)) ? String(displayTable).padStart(2, '0') : displayTable;
  const groups = activeCategory === 'all' && !search.trim()
    ? [...categories.map(c => ({ key: c.id, title: c.name, list: filtered.filter(i => String(i.category) === String(c.id)) })),
      { key: 'other', title: 'Khác', list: filtered.filter(i => !categories.some(c => String(c.id) === String(i.category))) }].filter(g => g.list.length)
    : [{ key: 'flat', title: '', list: filtered }];
  const liveItems = (order?.items || []).filter(i => i.status !== 'cancelled');
  const allServed = order?.status === 'completed' || (liveItems.length > 0 && liveItems.every(i => i.status === 'served'));
  const stage = allServed ? STEPS.length : liveItems.some(i => ['cooking', 'done', 'served'].includes(i.status)) ? 1 : 0;
  const heroItem = items.find(i => i.image_url);
  const icon = name => <span className="material-symbols-outlined" aria-hidden="true">{name}</span>;

  if (accessError) return <div className={styles.page}>
    <header className={styles.header}><div className={styles.headerInner}>
      <span className={styles.brand} aria-label="ABC Restaurant"><span className={styles.mono} aria-hidden="true">ABC</span><span className={styles.wordmark}>ABC Restaurant</span></span>
    </div></header>
    <main className={styles.main}><div className={`empty ${styles.accessError}`} role="alert">
      <span className="material-symbols-outlined empty-icon" aria-hidden="true">qr_code_scanner</span>
      <p className="empty-title">Không mở được bàn</p>
      <p>Liên kết QR thiếu mã hoặc đã hết hiệu lực. Vui lòng quét lại mã QR đặt trên bàn, hoặc nhờ nhân viên hỗ trợ.</p>
    </div></main>
  </div>;

  return <div className={styles.page}>
    <header className={styles.header}><div className={styles.headerInner}>
      <a href={`/table/${displayTable}`} className={styles.brand} aria-label="ABC Restaurant"><span className={styles.mono} aria-hidden="true">ABC</span><span className={styles.wordmark}>ABC Restaurant</span></a>
      <div className={styles.headerActions}>
        <span className={styles.tableBadge}>Bàn {tableLabel}</span>
        <button type="button" className={styles.callBtn} onClick={() => setShowService(true)}>{icon('room_service')}Gọi phục vụ</button>
      </div>
    </div></header>

    <section className={styles.hero}>
      {heroItem && <img className={styles.heroImg} src={imageSrc(heroItem)} alt="" />}
      <div className={styles.heroShade} />
      <div className={styles.heroInner}>
        <span className={styles.eyebrow}>Thực đơn</span>
        <h1>ABC Restaurant</h1>
        <p>Hương vị Việt, nấu mỗi ngày</p>
        <span className={styles.heroTable}>{icon('table_restaurant')}Bàn {tableLabel}{table?.area ? ` · ${table.area}` : ''}</span>
      </div>
    </section>

    <div className={styles.chipBar}><div className={styles.chipBarInner} role="tablist" aria-label="Danh mục">
      <button type="button" role="tab" aria-selected={activeCategory === 'all'} className={`chip ${styles.chipBtn}`} onClick={() => setActiveCategory('all')}>Tất cả</button>
      {categories.map(c => <button type="button" role="tab" key={c.id} aria-selected={activeCategory === String(c.id)} className={`chip ${styles.chipBtn}`} onClick={() => setActiveCategory(String(c.id))}>{c.name}</button>)}
    </div></div>

    <main className={styles.main}>
      <div className={styles.searchWrap}>
        {icon('search')}
        <input className={`input ${styles.search}`} type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tìm món hoặc đồ uống" aria-label="Tìm món" />
      </div>

      {order && <section className={styles.order} aria-label="Đơn hàng của bàn">
        <div className={styles.orderHead}>
          <div>
            <div className={styles.orderTitle}>Đơn <span className="num">#{order.id}</span>{order.status === 'completed' && <span className="badge badge-ok">Đã thanh toán</span>}{order.status === 'cancelled' && <span className="badge badge-danger">Đã huỷ</span>}</div>
            <div className={styles.orderMeta}>Bàn {order.table_number} · <span className="num">{vnd(order.total_amount)}</span></div>
          </div>
          <div className={styles.orderActions}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowBill(true)}>Hóa đơn tạm tính</button>
            {payable && <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowPayment(true)}>Thanh toán</button>}
            {order.status === 'completed' && <button type="button" className="btn btn-primary btn-sm" onClick={() => { setMessage(''); setShowReview(true); }}>Đánh giá</button>}
          </div>
        </div>
        {order.status !== 'cancelled' && liveItems.length > 0 && <ol className={styles.steps}>
          {STEPS.map((s, idx) => <li key={s} className={`${styles.step} ${idx < stage ? styles.stepDone : ''} ${idx === stage ? styles.stepNow : ''}`} aria-current={idx === stage ? 'step' : undefined}>
            <span className={styles.stepDot} aria-hidden="true" />{s}
          </li>)}
        </ol>}
        <ul className={styles.orderItems}>{order.items?.map(i => <li key={i.id} className={styles.orderItem}>
          <span className={styles.orderItemName}><span className="num">{i.quantity}×</span> {i.menu_item_name}</span>
          <span className={`badge ${ITEM_BADGE[i.status] || 'badge-neutral'}`}>{ITEM_STATUS[i.status] || i.status}</span>
          {payable && i.status === 'pending' && <button type="button" className={styles.cancelItem} disabled={busy} onClick={() => cancelItem(i)} aria-label={`Huỷ ${i.menu_item_name}`}>Huỷ</button>}
        </li>)}</ul>
      </section>}

      {loading && <div className={styles.list} aria-busy="true" aria-label="Đang tải thực đơn">
        {[0, 1, 2, 3].map(i => <div key={i} className={styles.card}><span className={`skeleton ${styles.thumb}`} /><div className={styles.cardBody}><span className="skeleton" style={{ width: '70%', height: 18 }} /><span className="skeleton" style={{ width: '90%' }} /><span className="skeleton" style={{ width: '40%' }} /></div></div>)}
      </div>}

      {failed && <div className="empty">
        <span className="material-symbols-outlined empty-icon" aria-hidden="true">cloud_off</span>
        <p className="empty-title">Không tải được thực đơn</p>
        <p>Kiểm tra kết nối mạng hoặc quét lại mã QR trên bàn.</p>
        <button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Tải lại</button>
      </div>}

      {!loading && !failed && groups.map(g => <section key={g.key} className={styles.group}>
        {g.title && <h2 className={styles.groupTitle}><span>{g.title}</span><small className="num">{g.list.length} món</small></h2>}
        <div className={styles.list}>{g.list.map(item => {
          const qty = cartQty(item.id);
          return <article className={styles.card} key={item.id}>
            <div className={styles.thumb}>{item.image_url ? <img src={imageSrc(item)} alt={item.name} loading="lazy" /> : <span className="material-symbols-outlined" aria-hidden="true">restaurant</span>}</div>
            <div className={styles.cardBody}>
              <h3>{item.name}</h3>
              {item.description && <p>{item.description}</p>}
              <div className={styles.rowFoot}>
                <span className={`num ${styles.price}`}>{vnd(item.price)}</span>
                <button type="button" className={styles.addBtn} onClick={() => add(item)} aria-label={`Thêm ${item.name}${qty ? `, đang có ${qty} trong giỏ` : ''}`}>{qty ? <span className="num">{qty}</span> : icon('add')}</button>
              </div>
            </div>
          </article>;
        })}</div>
      </section>)}

      {!loading && !failed && !filtered.length && <div className="empty">
        <span className="material-symbols-outlined empty-icon" aria-hidden="true">search_off</span>
        <p className="empty-title">{search.trim() ? `Không có món khớp "${search.trim()}"` : 'Chưa có món trong mục này'}</p>
        <p>Thử từ khoá khác hoặc chọn danh mục khác.</p>
        {(search || activeCategory !== 'all') && <button type="button" className="btn btn-secondary" onClick={() => { setSearch(''); setActiveCategory('all'); }}>Xem tất cả món</button>}
      </div>}
    </main>

    {message && <div className={styles.notice} role="status"><span>{message}</span><button type="button" onClick={() => setMessage('')} aria-label="Đóng thông báo">{icon('close')}</button></div>}

    {count > 0 && <div className={styles.dock}><div className={styles.dockInner}><div className={styles.dockInfo}><b><span className={`num ${styles.countBubble}`}>{count}</span> món</b><span className="num">{vnd(total)}</span></div><button type="button" className="btn btn-primary btn-lg" onClick={() => setShowCart(true)}>Xem giỏ</button></div></div>}
    {count === 0 && payable && <div className={styles.dock}><div className={styles.dockInner}><div className={styles.dockInfo}><b>Đơn <span className="num">#{order.id}</span></b><span className="num">{vnd(order.total_amount)}</span></div><button type="button" className="btn btn-primary btn-lg" onClick={() => setShowPayment(true)}>Thanh toán</button></div></div>}

    {showCart && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowCart(false)}>
      <form className="modal" onSubmit={checkout} role="dialog" aria-modal="true" aria-label="Giỏ hàng">
        <div className="modal-head"><h2 className="modal-title">Giỏ hàng</h2><button type="button" className="modal-close" onClick={() => setShowCart(false)} aria-label="Đóng">{icon('close')}</button></div>
        <div className={styles.cartList}>{cart.map(x => <div className={styles.cartRow} key={x.id}>
          <div className={styles.cartInfo}><b>{x.name}</b><span className="num">{vnd(x.price)}</span></div>
          <div className={styles.qty}><button type="button" onClick={() => changeQty(x.id, -1)} aria-label={`Giảm ${x.name}`}>{icon('remove')}</button><span className="num" aria-live="polite">{x.quantity}</span><button type="button" onClick={() => changeQty(x.id, 1)} aria-label={`Tăng ${x.name}`}>{icon('add')}</button></div>
        </div>)}</div>
        <div className="field"><label htmlFor="cart-note">Ghi chú cho bếp</label><textarea id="cart-note" className="textarea" value={note} onChange={e => setNote(e.target.value)} placeholder="Ví dụ: ít cay, không hành" /></div>
        <div className="field"><label htmlFor="cart-promo">Mã khuyến mãi</label><input id="cart-promo" className="input" value={promoCode} onChange={e => setPromoCode(e.target.value)} placeholder="Nhập mã nếu có" autoCapitalize="characters" /></div>
        <div className={styles.totalRow}><span>Tạm tính</span><b className="num">{vnd(total)}</b></div>
        <button className="btn btn-primary btn-lg btn-block" disabled={busy} aria-busy={busy}>{busy ? 'Đang gửi…' : `Gửi đơn · ${vnd(total)}`}</button>
        <p className={styles.smallPrint}>Bạn có thể thanh toán sau, bằng nút "Thanh toán" trên màn hình thực đơn.</p>
      </form>
    </div>}

    {showService && <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowService(false)}>
      <section className="modal" role="dialog" aria-modal="true" aria-label="Gọi phục vụ">
        <div className="modal-head"><h2 className="modal-title">Gọi nhân viên phục vụ</h2><button type="button" className="modal-close" onClick={() => setShowService(false)} aria-label="Đóng">{icon('close')}</button></div>
        <div className={styles.requestList}>{['Cần hỗ trợ tại bàn', 'Yêu cầu thêm nước', 'Yêu cầu thêm dụng cụ', 'Yêu cầu thanh toán'].map(x => <button type="button" key={x} onClick={() => sendCall(x)}><span>{x}</span>{icon('chevron_right')}</button>)}</div>
        <div className="field"><label htmlFor="custom-call">Yêu cầu khác</label><textarea id="custom-call" className="textarea" placeholder="Nhập yêu cầu của bạn" /></div>
        <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => sendCall(document.getElementById('custom-call')?.value || 'Khách cần hỗ trợ')}>Gửi yêu cầu</button>
      </section>
    </div>}

    {confirmDialog}
    {showReview && order && <ReviewModal order={order} onClose={() => setShowReview(false)} onReviewed={() => setToast('Cảm ơn bạn đã đánh giá!')} />}
    <Toast message={toast} visible={Boolean(toast)} onHide={() => setToast('')} />
    {showBill && order && <BillModal order={order} onClose={() => setShowBill(false)} onPay={() => setShowPayment(true)} />}

    {showPayment && order && <PaymentModal
      orderId={order.id}
      onClose={() => setShowPayment(false)}
      onPaid={() => { setOrder(o => o && { ...o, status: 'completed', payment_status: 'success' }); setMessage(`Đơn #${order.id} đã thanh toán thành công. Cảm ơn quý khách!`); }}
    />}
  </div>;
}
