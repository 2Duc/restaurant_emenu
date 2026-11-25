import { useState, useCallback, useRef, useEffect } from "react";
import { api, connectSocket, logout, getUser, getRole } from "../../services/api";
import MaterialIcon from "../../shared/MaterialIcon";
import styles from "../Chef/styles.module.css";

export default function Chef() {
  const user = getUser();
  const canServe = ['QL', 'AD'].includes(getRole());   // chỉ phục vụ/quản lý được xác nhận "đã phục vụ" (backend kiểm tra)
  const [activeStation, setActiveStation] = useState("all");   // lọc theo danh mục món (quầy)
  const [categories, setCategories] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [menuItems, setMenuItems] = useState([]);
  const [hotPass, setHotPass] = useState([]);
  const [history, setHistory] = useState([]);
  const [kpi, setKpi] = useState({ pending: 0, cooking: 0, servedToday: 0, avgWait: 0 });
  const [wsLive, setWsLive] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [apiError, setApiError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [toast, setToast] = useState({
    visible: false,
    message: "",
    icon: "check_circle",
  });
  const refreshKitchen = useCallback(async () => {
    try {
      const [response, cats, menu] = await Promise.all([
        api.get('/orders/?active=1&limit=300'), api.get('/categories/'), api.get('/menu-items/?ordering=name'),
      ]);
      const orders = response.results || response;
      setCategories(cats.results || cats);
      setMenuItems(menu.results || menu);
      const open = orders.filter(o => !['completed', 'cancelled'].includes(o.status));
      const mapped = open.filter(o => (o.items || []).some(i => i.status !== 'served')).map(o => {
        const orderItems = (o.items || []).filter(i => i.status !== 'served');
        const pending = orderItems.some(i => i.status === 'pending');
        const cooking = orderItems.some(i => i.status === 'cooking');
        return {
          id: o.id, orderId: o.id, table: `BÀN ${o.table_number}`, code: `#KDS-${o.id}`, createdAt: o.created_at,
          status: pending ? 'new' : 'cooking', statusLabel: pending ? 'Mới nhận' : 'Đang chế biến',
          timer: new Date(o.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
          guests: 'Khách tại bàn', station: 'Bếp trung tâm',
          items: orderItems.map(i => ({ id: i.id, qty: i.quantity, name: i.menu_item_name, note: i.note, categoryId: i.category, stationTag: ({ pending: 'Chờ chế biến', cooking: 'Đang chế biến', done: 'Đã hoàn thành' })[i.status], stationType: i.status })),
          actions: pending ? ['start'] : cooking ? ['serve'] : [],
        };
      });
      setTickets(mapped);
      // Món đã xong, đang chờ phục vụ bưng ra (Hot Pass)
      setHotPass(open.flatMap(o => (o.items || []).filter(i => i.status === 'done').map(i => ({
        id: i.id, createdAt: o.created_at, table: `BÀN ${o.table_number}`, dish: `${i.quantity}× ${i.menu_item_name}`,
        meta: 'Đã xong • chờ phục vụ bưng ra', ready: true, readyNote: 'Món đã sẵn sàng tại quầy',
      }))));
      // Lịch sử món đã ra (đã phục vụ), mới nhất trước
      const served = orders.flatMap(o => (o.items || []).filter(i => i.status === 'served').map(i => ({
        id: i.id, at: new Date(o.updated_at), name: `Bàn ${o.table_number}: ${i.quantity}× ${i.menu_item_name}`,
      }))).sort((a, b) => b.at - a.at);
      setHistory(served.slice(0, 15).map(x => ({ id: x.id, name: x.name, time: x.at.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }), detail: 'Trạng thái:', actor: 'Đã phục vụ', actorDefault: true, danger: false })));
      const nowMs = Date.now();
      setKpi({
        pending: mapped.filter(t => t.status === 'new').length,
        cooking: mapped.filter(t => t.status === 'cooking').length,
        servedToday: served.filter(x => x.at.toDateString() === new Date().toDateString()).length,
        avgWait: mapped.length ? Math.round(mapped.reduce((n, t) => n + (nowMs - new Date(t.createdAt).getTime()) / 60000, 0) / mapped.length) : 0,
      });
      setApiError('');
    } catch (e) { setApiError(e.message); }
    setLoaded(true);
  }, []);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshKitchen(); const timer = setInterval(refreshKitchen, 12000); const clock = setInterval(() => setNow(new Date()), 30000); const closeSocket = connectSocket('kitchen_orders', { onOpen: () => setWsLive(true), onClose: () => setWsLive(false), onMessage: () => refreshKitchen() });
    return () => { clearInterval(timer); clearInterval(clock); closeSocket(); };
  }, [refreshKitchen]);
  async function updateKitchenTicket(ticket, nextStatus) {
    try {
      await Promise.all(ticket.items.filter(i => i.stationType === (nextStatus === 'cooking' ? 'pending' : 'cooking')).map(i => api.patch(`/order-items/${i.id}/status/`, {status:nextStatus})));
      await refreshKitchen(); showToast(nextStatus === 'cooking' ? 'Đã nhận chế biến.' : 'Đã hoàn thành món và thông báo phục vụ.', 'check_circle');
    } catch (e) { setApiError(e.message); }
  }

  const toastTimer = useRef(null);

  const showToast = useCallback((message, icon = "check_circle") => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ visible: true, message, icon });
    toastTimer.current = setTimeout(() => {
      setToast((t) => ({ ...t, visible: false }));
    }, 3000);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  // Khoá / mở bán nhanh một món (86) — đồng bộ ngay với menu của khách
  const toggleSoldOut = async (item) => {
    try {
      await api.post(`/menu-items/${item.id}/availability/`, { is_available: !item.is_available });
      await refreshKitchen();
      showToast(item.is_available ? `Đã khóa 86: ${item.name}` : `Đã mở bán lại: ${item.name}`, item.is_available ? "lock" : "lock_open");
    } catch (e) { setApiError(e.message); }
  };

  const handleBung = async (h) => {
    try {
      await api.patch(`/order-items/${h.id}/status/`, { status: 'served' });
      await refreshKitchen();
      showToast(`Đã bưng: ${h.table} — ${h.dish}`, "room_service");
    } catch (e) { setApiError(e.message); }
  };

  const liveTickets = tickets.filter(t => t.items.some(i => i.stationType !== "done"));
  const stations = [
    { id: "all", label: "Tất cả", count: liveTickets.length },
    ...categories.map(c => ({ id: String(c.id), label: c.name, count: liveTickets.filter(t => t.items.some(i => String(i.categoryId) === String(c.id))).length })),
  ];
  const filteredTickets = activeStation === "all" ? tickets
    : tickets.map(t => ({ ...t, items: t.items.filter(i => String(i.categoryId) === activeStation) })).filter(t => t.items.length);
  const hour = now.getHours();
  const shiftLabel = hour < 11 ? "Ca Sáng" : hour < 15 ? "Ca Trưa" : hour < 18 ? "Ca Chiều" : "Ca Tối";
  const soldOutView = menuItems.map(i => ({ id: i.id, name: i.name, meta: `${i.category_name || "Món"} • ${Number(i.price).toLocaleString("vi-VN")}đ`, on: i.is_available, raw: i }));

  const waitMin = (t) => Math.max(0, Math.floor((now - new Date(t.createdAt)) / 60000));
  const waitTone = (m) => (m >= 20 ? styles.tDanger : m >= 10 ? styles.tWarn : "");
  const byAge = (a, b) => new Date(a.createdAt) - new Date(b.createdAt);
  const activeOnly = filteredTickets
    .map(t => ({ ...t, items: t.items.filter(i => i.stationType !== "done") }))
    .filter(t => t.items.length);
  const colNew = activeOnly.filter(t => t.status === "new").sort(byAge);
  const colCooking = activeOnly.filter(t => t.status === "cooking").sort(byAge);
  const roleLabel = { BEP: "Bộ phận bếp", QL: "Quản lý", AD: "Quản trị viên" }[getRole()] || "Nhân viên";

  const renderTicket = (ticket) => {
    const m = waitMin(ticket);
    return (
      <article key={ticket.id} className={`${styles.ticket} ${m >= 20 ? styles.ticketDanger : m >= 10 ? styles.ticketWarn : ""}`}>
        <header className={styles.ticketHead}>
          <div className={styles.ticketTable}>{ticket.table.replace("BÀN ", "Bàn ")}</div>
          <div className={styles.ticketTime}>
            <span className={`${styles.timer} ${waitTone(m)}`}><MaterialIcon name="timer" size={20} />{m} phút</span>
            <span className={styles.ticketMeta}>{ticket.code} · {ticket.timer}</span>
          </div>
        </header>
        <ul className={styles.items}>
          {ticket.items.map((item) => (
            <li key={item.id} className={styles.item}>
              <div className={styles.itemRow}>
                <span className={styles.qty}>{item.qty}×</span>
                <span className={styles.dish}>{item.name}</span>
                {item.stationType === "cooking" && ticket.status === "new" && <span className="badge badge-warn">Đang nấu</span>}
              </div>
              {item.note && <div className={styles.note}><MaterialIcon name="sticky_note_2" size={18} /><span>{item.note}</span></div>}
            </li>
          ))}
        </ul>
        {ticket.actions.includes("start") && (
          <button type="button" className={`btn btn-primary btn-lg btn-block ${styles.action}`} onClick={() => updateKitchenTicket(ticket, "cooking")}>
            Bắt đầu nấu
          </button>
        )}
        {ticket.actions.includes("serve") && (
          <button type="button" className={`btn btn-lg btn-block ${styles.action} ${styles.actionDone}`} onClick={() => updateKitchenTicket(ticket, "done")}>
            Xong, báo phục vụ
          </button>
        )}
      </article>
    );
  };

  const empty = <div className={styles.colEmpty}>Chưa có món nào</div>;
  const skeleton = [0, 1].map(i => <div key={i} className={`skeleton ${styles.skel}`} />);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.monogram} aria-hidden="true">ABC</span>
          <span className={styles.wordmark}>ABC Restaurant</span>
          <span className={styles.brandSub}>Màn hình bếp</span>
        </div>
        <div className={styles.stats} aria-label="Tổng quan">
          <span className={styles.stat}><b>{liveTickets.filter(t => t.status === "new").length}</b> chờ</span>
          <span className={styles.stat}><b>{liveTickets.filter(t => t.status === "cooking").length}</b> đang nấu</span>
          <span className={styles.stat}><b>{hotPass.length}</b> chờ bưng</span>
          <span className={styles.stat}><b>{kpi.servedToday}</b> đã ra hôm nay</span>
          <span className={styles.stat}>Chờ TB <b>{kpi.avgWait}</b> phút</span>
        </div>
        <div className={styles.headerRight}>
          <span className={styles.clock}><MaterialIcon name="schedule" size={18} /> {now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} · {shiftLabel}</span>
          <span className={`${styles.live} ${wsLive ? styles.liveOn : ""}`}><i className={styles.liveDot} />{wsLive ? "Trực tiếp" : "Đang kết nối lại…"}</span>
          <span className={styles.user}>{user?.username}<small>{roleLabel}</small></span>
          <button type="button" className={styles.logout} onClick={() => { logout(); window.location.href = '/login'; }}>Đăng xuất</button>
        </div>
      </header>

      <div className={styles.filters} role="group" aria-label="Lọc theo nhóm món">
        {stations.map((s) => (
          <button key={s.id} type="button" className={`chip ${activeStation === s.id ? "is-active" : ""}`} aria-pressed={activeStation === s.id} onClick={() => setActiveStation(s.id)}>
            {s.id === "all" ? "Tất cả" : s.label} <span className={styles.chipCount}>{s.count}</span>
          </button>
        ))}
      </div>

      {apiError && <div className={`alert alert-danger ${styles.error}`} role="alert">{apiError}</div>}

      <main className={styles.layout}>
        <div className={styles.board}>
          <section className={styles.col} aria-label="Chờ">
            <h2 className={styles.colHead}>Chờ<span className={styles.colCount}>{colNew.length}</span></h2>
            <div className={styles.colBody}>{!loaded ? skeleton : colNew.length ? colNew.map(renderTicket) : empty}</div>
          </section>
          <section className={styles.col} aria-label="Đang nấu">
            <h2 className={styles.colHead}>Đang nấu <span className={styles.colCount}>{colCooking.length}</span></h2>
            <div className={styles.colBody}>{!loaded ? skeleton : colCooking.length ? colCooking.map(renderTicket) : empty}</div>
          </section>
          <section className={styles.col} aria-label="Xong">
            <h2 className={styles.colHead}>Xong, chờ bưng <span className={styles.colCount}>{hotPass.length}</span></h2>
            <div className={styles.colBody}>
              {!loaded ? skeleton : hotPass.length ? hotPass.map((h) => (
                <article key={h.id} className={`${styles.ticket} ${styles.ticketDone}`}>
                  <div className={styles.doneRow}>
                    <span className={styles.ticketTable}>{h.table.replace("BÀN ", "Bàn ")}</span>
                    <span className={`${styles.timer} ${waitTone(waitMin(h))}`}><MaterialIcon name="timer" size={20} />{waitMin(h)} phút</span>
                  </div>
                  <div className={styles.doneDish}>{h.dish}</div>
                  {canServe && <button type="button" className={`btn btn-secondary btn-lg btn-block ${styles.action}`} onClick={() => handleBung(h)}>Đã bưng</button>}
                </article>
              )) : empty}
            </div>
          </section>
        </div>

        <aside className={styles.rail}>
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>Tình trạng món <span className={styles.panelCount}>Đang hết: {soldOutView.filter(x => !x.on).length}</span></h2>
            <ul className={styles.list}>
              {soldOutView.length === 0 && <li className={styles.listEmpty}>Chưa có món nào</li>}
              {soldOutView.map((item) => (
                <li key={item.id} className={styles.row}>
                  <div className={styles.rowText}>
                    <span className={`${styles.rowName} ${!item.on ? styles.rowOff : ""}`}>{item.name}</span>
                    <span className={styles.rowMeta}>{item.meta}</span>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={item.on}
                    aria-label={`${item.name}: ${item.on ? "còn" : "hết"}`}
                    className={`${styles.switch} ${item.on ? styles.switchOn : ""}`}
                    onClick={() => toggleSoldOut(item.raw)}
                  ><span className={styles.knob} /><span className={styles.switchText}>{item.on ? "Còn" : "Hết"}</span></button>
                </li>
              ))}
            </ul>
          </section>
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>Đã ra gần đây</h2>
            <ul className={styles.list}>
              {history.length === 0 && <li className={styles.listEmpty}>Chưa có món nào</li>}
              {history.map((a) => (
                <li key={a.id} className={styles.row}>
                  <span className={styles.rowName}>{a.name}</span>
                  <span className={styles.rowMeta}>{a.time}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </main>

      <div className={`toast toast-ok ${toast.visible ? "" : "toast-hidden"}`} role="status" aria-live="polite">{toast.message}</div>
    </div>
  );
}
