import { useCallback, useEffect, useState } from "react";
import { api, getUser, getRole, logout, connectSocket } from "../../services/api";
import MaterialIcon from "../../shared/MaterialIcon";
import Toast from "../../shared/Toast";
import ManagerReports from "../ManagerReports/ManagerReports";
import ManagerMenu from "../ManagerMenu/ManagerMenu";
import ManagerTables from "../ManagerTables/ManagerTables";
import ManagerPromotions from "../ManagerPromotions/ManagerPromotions";
import ManagerOrders from "../ManagerOrders/ManagerOrders";
import ManagerPayments from "../ManagerPayments/ManagerPayments";
import ManagerStaff from "../ManagerStaff/ManagerStaff";
import ManagerSettings from "../ManagerSettings/ManagerSettings";
import ManagerAudit from "../ManagerAudit/ManagerAudit";
import ManagerReviews from "../ManagerReviews/ManagerReviews";
import ChangePasswordModal from "../../components/ChangePasswordModal/ChangePasswordModal";
import styles from "../Manager/styles.module.css";

const NAV_ITEMS = [
  { id: "kpi", label: "Tổng quan", icon: "query_stats" },
  { id: "menu", label: "Thực đơn", icon: "restaurant_menu" },
  { id: "tables", label: "Bàn & mã QR", icon: "table_restaurant" },
  { id: "promo", label: "Khuyến mãi", icon: "confirmation_number" },
  { id: "orders", label: "Đơn hàng", icon: "receipt_long" },
  { id: "reviews", label: "Đánh giá", icon: "reviews" },
  { id: "sandbox", label: "Đối soát giao dịch", icon: "account_balance_wallet" },
  { id: "staff", label: "Nhân viên", icon: "manage_accounts" },
  { id: "settings", label: "Cấu hình hệ thống", icon: "settings", adminOnly: true },
];
const ROLE_LABEL = { QL: "Quản lý", AD: "Quản trị viên" };

export default function Manager({ initialNav = "kpi" }) {
  const user = getUser();
  const isAdmin = getRole() === "AD";
  const navItems = NAV_ITEMS.filter((i) => !i.adminOnly || isAdmin);
  const [activeNav, setActiveNav] = useState(navItems.some((i) => i.id === initialNav) ? initialNav : "kpi");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [switchModal, setSwitchModal] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [liveTick, setLiveTick] = useState(0);   // tăng mỗi khi có sự kiện real-time → các bảng tự làm mới
  const [unread, setUnread] = useState(0);
  const [toast, setToast] = useState({ visible: false, message: "", icon: "check_circle" });

  const showToast = useCallback((message, icon = "check_circle") => setToast({ visible: true, message, icon }), []);
  const hideToast = useCallback(() => setToast((t) => ({ ...t, visible: false })), []);

  // Real-time: nhận đơn mới, đổi trạng thái món/đơn, thanh toán, gọi phục vụ qua WebSocket.
  useEffect(() => {
    const labels = {
      new_order: ["Có đơn hàng mới", "receipt_long"],
      order_updated: ["Đơn hàng vừa được cập nhật", "sync"],
      item_status_updated: [null, null],
      staff_call: ["Khách gọi phục vụ", "notifications_active"],
    };
    return connectSocket("staff_orders", { onMessage: (e) => {
        let data; try { data = JSON.parse(e.data); } catch { return; }
        setLiveTick((n) => n + 1);
        const [text, icon] = labels[data.type] || [null, null];
        if (text) { setUnread((n) => n + 1); showToast(text, icon); }
    } });
  }, [showToast]);

  async function confirmSwitchMode() {
    try { await api.post("/audit-logs/", { action: "SWITCH_MODE", mode: "waiter", reason: "Hỗ trợ phục vụ" }); } catch { /* vẫn cho chuyển chế độ */ }
    window.location.href = "/staff";
  }
  const doLogout = () => { logout(); window.location.href = "/login"; };

  const panel = {
    kpi: <ManagerReports refreshKey={liveTick} />,
    menu: <ManagerMenu />,
    tables: <ManagerTables refreshKey={liveTick} />,
    promo: <ManagerPromotions />,
    orders: <ManagerOrders refreshKey={liveTick} />,
    reviews: <ManagerReviews refreshKey={liveTick} />,
    sandbox: <ManagerPayments refreshKey={liveTick} />,
    staff: <ManagerStaff />,
    settings: isAdmin ? <ManagerSettings /> : null,
  }[activeNav];

  const title = navItems.find((i) => i.id === activeNav)?.label;

  return (
    <div className={styles.page}>
      <div className={`${styles.scrim} ${sidebarOpen ? styles.scrimVisible : ""}`} onClick={() => setSidebarOpen(false)} role="presentation" />

      <aside className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.sidebarTop}>
          <div className={styles.brand}><span className={styles.monogram} aria-hidden="true">ABC</span><div className={styles.brandText}><div className={styles.brandName}>ABC Restaurant</div><div className={styles.brandSub}>Quản lý</div></div></div>
          <div className={styles.navLabel}>Vận hành</div>
          <nav className={styles.nav} aria-label="Chức năng quản lý">
            {navItems.map((item) => (
              <button key={item.id} type="button" className={`${styles.navItem} ${activeNav === item.id ? styles.navItemActive : ""}`}
                aria-current={activeNav === item.id ? "page" : undefined}
                onClick={() => { setActiveNav(item.id); setSidebarOpen(false); }}>
                <MaterialIcon name={item.icon} size={20} /><span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>
        <div className={styles.sidebarBottom}>
          <button type="button" className={styles.sideLink} onClick={() => setSwitchModal(true)}><MaterialIcon name="sync_alt" size={20} /><span>Sang chế độ Phục vụ</span></button>
          <button type="button" className={styles.sideLink} onClick={() => setPwOpen(true)}><MaterialIcon name="key" size={20} /><span>Đổi mật khẩu</span></button>
          <button type="button" className={`${styles.sideLink} ${styles.sideLinkDanger}`} onClick={doLogout}><MaterialIcon name="logout" size={20} /><span>Đăng xuất</span></button>
        </div>
      </aside>

      <div className={styles.shell}>
        <header className={styles.topbar}>
          <div className={styles.topLeft}>
            <button type="button" className={`${styles.iconBtn} ${styles.menuToggle}`} aria-label="Mở menu" onClick={() => setSidebarOpen(true)}><MaterialIcon name="menu" size={22} /></button>
            <h1 className={styles.pageTitle}>{title}</h1>
          </div>
          <div className={styles.topRight}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAuditOpen(true)}><MaterialIcon name="history" size={18} /><span className={styles.auditLabel}>Nhật ký thao tác</span></button>
            <button type="button" className={styles.iconBtn} aria-label={unread > 0 ? `Thông báo, ${unread} mới` : "Thông báo"} onClick={() => setUnread(0)}>
              <MaterialIcon name="notifications" size={22} />{unread > 0 && <span className={styles.notifDot} />}
            </button>
            <div className={styles.user}>
              <div className={styles.userText}><div className={styles.userName}>{user?.username}</div><div className={styles.userRole}>{ROLE_LABEL[user?.role]}</div></div>
              <div className={styles.avatar}><MaterialIcon name="person" size={18} /></div>
            </div>
          </div>
        </header>

        <main className={styles.main}><div className={styles.content}>{panel}</div></main>
      </div>

      {switchModal && (
        <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) setSwitchModal(false); }} role="presentation">
          <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="switch-title">
            <div className="modal-head"><h2 className="modal-title" id="switch-title">Chuyển sang chế độ phục vụ?</h2></div>
            <p className={styles.modalText}>
              Hệ thống mở giao diện <strong>/staff</strong> và ghi nhật ký{" "}
              <code className={styles.code}>acted_by=&quot;{user?.username}&quot;, acted_mode=&quot;waiter&quot;</code>.
              Bạn có thể quay lại chế độ quản lý ngay trên màn hình phục vụ.
            </p>
            <div className="modal-foot">
              <button type="button" className="btn btn-secondary" onClick={() => setSwitchModal(false)}>Huỷ</button>
              <button type="button" className="btn btn-primary" onClick={confirmSwitchMode}>Xác nhận chuyển</button>
            </div>
          </div>
        </div>
      )}

      <ManagerAudit open={auditOpen} onClose={() => setAuditOpen(false)} />
      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}

      <Toast visible={toast.visible} message={toast.message} icon={toast.icon} onHide={hideToast} />
    </div>
  );
}
