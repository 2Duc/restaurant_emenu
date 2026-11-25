# PROGRESS — đối chiếu BRD (C:\Users\Admin\Downloads\BRD-yeu-cau-nghiep-vu.md)

Cập nhật: 2026-11-24

## TRẠNG THÁI HIỆN TẠI (đọc đầu tiên khi mở phiên mới)
Cập nhật: 2026-11-24 cuối phiên
- Backend + BRD: XONG. Test 51/51 (sqlite). PostgreSQL 18 cổng 5433 (backend/.env), Redis Docker `emenu-redis` :6379.
- Giao diện: XONG & ĐÃ DUYỆT — option A "Basil Soft" (mẫu: ui-preview/options/option-a-basil-soft.html; spec: frontend/DESIGN.md mục "CHỐT CUỐI ... lần 5"). Font Newsreader + Plus Jakarta Sans. Tên quán "ABC Restaurant".
- XONG thêm: nút "Đánh giá" sau khi đơn completed (Menu.jsx → ReviewModal, review theo từng order_item); ConfirmDialog/PromptDialog + useConfirm thay mọi window.confirm/prompt; route /table/:tableId cho link QR.
- Không còn việc dở. Việc tuỳ chọn: VNPay sandbox khi có khoá.
- Quy tắc người dùng: KHÔNG xoá dữ liệu có sẵn (giữ bàn 9 PREVIEW, bàn 10); chỉ xoá dữ liệu test tự tạo (tiền tố uitest_/uidesign_). KHÔNG đổi nội dung chữ, chỉ sửa giao diện. Có thay đổi UI → cập nhật ui-preview/ cho người dùng duyệt trước.
- Server dev đang chạy lúc cuối phiên (có thể đã tắt): backend daphne 127.0.0.1:8000, Vite localhost:5173, static ui-preview 127.0.0.1:5190.
  - [x] Gắn ReviewModal: nút "Đánh giá" ở thẻ đơn (Menu) khi đơn completed, toast cảm ơn; thay window.confirm/prompt bằng ConfirmDialog/PromptDialog/useConfirm (components/ConfirmDialog) ở Menu, Waiter, Manager Menu/Orders/Promotions/Tables; thêm route /table/:tableId
- [x] Đã thử bấm trên Chrome mọi hộp thoại xác nhận/nhập (Menu, Waiter, ManagerMenu món+danh mục, Orders, Promotions, Tables sửa+xoá): Esc/nền/Huỷ/Enter đều OK; sửa ManagerOrders: confirmDialog bị hoá đơn che (đặt render sau modal hoá đơn). Dữ liệu uitest_ đã dọn, bàn 9/10 còn.
- Hoãn: VNPay sandbox thật (thiếu TMN_CODE/HASH_SECRET). Ngoài phạm vi: MoMo/ZaloPay.

## Phiên 2026-11-25 (đối chiếu BRD lần 2)
- [x] Vá bảo mật (RATE-01/03, AUTH-05, WS-02, SEC-02, tham số sai kiểu->400, JSONRenderer khi DEBUG=0, HSTS/CSP, PAY-02): Table.qr_token + link QR `?k=` + token phiên bàn `X-Table-Token` (migration 0008-0010), nút "Đổi mã QR", `NUM_PROXIES`, throttle theo bàn, `.gitignore`; test BE 248/248, FE 51/51; functional/security_scan.py sửa theo token mới; ui-preview 08-10 chờ duyệt; CHƯA chạy lại load/security/functional/docker - bước sau: in lại QR, chạy lại các bộ test, đặt NUM_PROXIES=1 trên Railway.
- [x] VNPay sandbox thật: khoá CAG0U1JV vào backend/.env (PAYMENT_GATEWAY_MODE=vnpay); link sandbox ký đúng (đã đối chứng ký sai → "Sai chữ ký"); vnpay-return tự cập nhật (idempotent với IPN)
- [x] Cổng giả lập PAYMENT_GATEWAY_MODE=mock (mặc định khi thiếu khoá): route FE /payment/mock (MockGateway), POST /api/payments/mock-callback/ (404 khi mode vnpay), `_settle_pending` dùng chung IPN; ui-preview/screenshots/06,07
- [x] vnpay_services `_post_merchant_api`: OSError/RequestException → VNPayError (biến REQUESTS_CA_BUNDLE sai không còn gây 500); test 55/55, eslint + vite build OK
- [x] Compose dùng HOST_IP/FRONTEND_PORT (.env gốc + .env.example); README có mục compose + test QR điện thoại + netsh firewall (chỉ ghi hướng dẫn, chưa chạy). .env gốc: HOST_IP=192.168.1.38, FRONTEND_PORT=8088 (cổng 8080 bị Apache PEM của EDB chiếm, PID httpd), mode vnpay
- [x] `docker compose up -d --build` OK (db/redis không map cổng ra host; emenu-redis giữ nguyên); seed_demo + admin_demo (AD) tạo trong DB compose; mật khẩu demo = SEED_DEMO_PASSWORD trong .env gốc
- [x] Chuyển dữ liệu local -> compose: pg_dump PG18 (lọc 
estrict/transaction_timeout) restore vào pg16, copy backend/media vào volume media (122 file); đối chiếu Category 8/MenuItem 62 (60 ảnh)/Table 30/Promo 6/User 10/Order 1 khớp nguồn; seed_demo + admin_demo (AD) chạy lại, đã xoá 2 món + 2 danh mục do seed_demo thêm; dump đã xoá
- [x] Kiểm tra: web http://192.168.1.38:8088 200, /api/menu-items/ 200, QR bàn = http://192.168.1.38:8088/table/<id>; Chrome Browser 1: đặt món (ghi chú TEST-LAN-QR, đơn #1 bàn 1), bếp thấy, đổi trạng thái -> khách cập nhật realtime (WS OK)
- [ ] Dừng ở trang sandbox VNPay NCB (đã nhập thẻ test, tên, 07/15) vì hộp "Điều khoản sử dụng" cần chấp nhận điều khoản -> chờ người dùng đồng ý; sau đó nhập OTP 123456, kiểm tra payment success + báo cáo. Chưa thử trang QR (Tải QR/In) trên UI
- Lưu ý: UI đăng nhập/thanh toán test chạy từ http://localhost:8088 (không phải IP LAN) theo quy tắc an toàn
- Lưu ý: Docker Desktop tắt → Redis tắt; chạy daphne local tạm với `REDIS_URL=` (InMemory)
- [x] Unit test: BE api/tests_unit/ +157 (212/212 PASS, coverage 88%), FE vitest +41 (41/41, coverage 96.5%; tách Menu/cartUtils.js); docs/testing/unit/ (README + screenshots + coverage html); `npm test`, backend/.coveragerc
- [x] README gốc, frontend/README.md, docker-compose.yml (db pg16, redis, backend :8000, frontend nginx :8080, mock mặc định), backend/{Dockerfile,Procfile,railway.json,.dockerignore}, frontend/{Dockerfile,nginx.conf,.dockerignore}; `compose config` OK; 54/54 test, vite build OK
- [ ] Chưa build thử compose (Docker Desktop tắt). Railway/Vercel CLI chưa cài → deploy thật chờ người dùng
- [ ] Chưa giao: seed_demo mở rộng (50–100 món, 6–10 danh mục, 20–30 bàn, ảnh); chuyển khoản thủ công riêng; màn hình cấu hình Admin

- [x] 2026-11-25: Chuyển khoản ngân hàng thủ công (Payment.bank_transfer, VietQR EMVCo, confirm-manual, migration 0011 đã áp DB local) + SystemSetting/màn Cấu hình hệ thống (AD, /api/settings/, /manager/settings); BE 274/274, FE 70/70, eslint+build OK, functional +4 TC (033-036 Pass); ui-preview 13-17 chờ duyệt; docker compose chưa rebuild/migrate; ManagerOrders METHOD chưa có nhãn bank_transfer (thuộc builder phân trang).
- [x] 2026-11-25: Functional test: docs/testing/functional/ (test-scenarios.md/.xlsx, run_functional.py, results.json, screenshots/) — 81 TC: 74 Pass, 0 Fail, 7 thủ công chưa chạy; đã sửa menu_view.availability (giá trị rác → 400) + test KitchenApiTests (backend 213/213 OK); VNPay sandbox thật (thẻ NCB, đơn #20) ghi Pass bằng chứng chạy tay
- [x] 2026-11-25: management command api/management/commands/seed_tables_promos.py (idempotent): bàn 1-30 (Khu A 1-12, Khu B 13-24, Sân vườn 25-30; tạo pk tường minh + setval sequence), 6 mã KM (ABC10, GIAM50K, MON15, MON10K, HETHAN20 hết hạn, SAPRA15 chưa kích hoạt). Đã chạy trên DB local; test 55/55.
- [x] 2026-11-25: Load test (Locust, docs/testing/load/) + Security test (docs/testing/security/, security_scan.py 54 kiểm tra: 39 đạt/10 không đạt/5 thông tin; bandit/pip-audit/npm audit sạch): điểm nghẽn = kết nối PG tăng theo số request đồng thời (daphne+ASGI, 200 user -> 'too many clients' -> 63% 500); lỗ hổng chính: throttle login bypass bằng X-Forwarded-For, X-Table-Id tự khai, WS table_<id> không xác thực, 500 khi tham số lọc sai kiểu; DB e_menu_load đã drop, server 8030/8031 đã tắt; chưa sửa code ứng dụng.
## Đã làm
- [x] requirements.txt: thêm channels, channels-redis, daphne, whitenoise, django-filter, qrcode, Pillow, requests
- [x] Xoá module trùng/lỗi import: api/realtime.py, api/orders.py, api/audit.py, api/scope.py (bản đúng nằm ở api/services/)
- [x] settings: DATABASE_URL hỗ trợ sqlite:/// (chỉ để chạy test), throttle rates
- [x] models: Order.created_by (ERD USER→ORDER), index created_at/paid_at/is_available, (table,status); Review rating 1–5; FK category/table → PROTECT
- [x] permissions: IsStaffMember, IsAdmin, has_role
- [x] services/realtime: broadcast sau commit (new_order, order_updated, item_status, staff_call, table_updated, menu_updated)
- [x] consumers: thêm table_updated, menu_updated, ping
- [x] services/scope: BR-02 ensure_table_scope, customer_table_id
- [x] services/orders: compute_discount, recalc_order, release_table_if_idle
- [x] auth_view: throttle login, ReauthAPIView, ChangePasswordAPIView (urls đã tham chiếu nhưng chưa có)
- [x] menu_view: avg_rating, /availability/ (bếp), xoá món đã bán → 409, xoá danh mục còn món → 400, audit
- [x] order_view: BR-02 scope, gộp đơn mở theo bàn, recalc khi gọi thêm, lọc q/date/limit, chuyển trạng thái đơn hợp lệ, /order-items/{id}/cancel/
- [x] promotion_view: quản lý thấy mọi mã, mã theo món (BR-05), scope, recalc + broadcast
- [x] payment_view: scope, broadcast khi thanh toán xong, GET /api/payments/ (quản lý), audit hoàn tiền / thu tiền mặt
- [x] report_view: period day/week/month/custom, series, best_sellers, peak_hours, methods, trừ tiền hoàn (BR-09)
- [x] review_view: scope khách, lọc order_id/menu_item/rating
- [x] staff_call_view: scope, chống spam, chuyển trạng thái hợp lệ, broadcast
- [x] table_view: scope current-order, không xoá bàn có đơn, không trả bàn trống khi còn đơn mở, audit
- [x] serializers: validate giá/ảnh/sức chứa/danh mục, chỉ AD cấp quyền AD

- [x] migration 0007_brd_alignment (gồm cả drift cũ: promotion.menu_item, auditlog.actor, table.number unique)
- [x] `manage.py test api`: 37/37 OK (sqlite)
- [x] Không broadcast `table_updated` khi tạo đơn / thanh toán (client suy ra từ new_order / order_updated)

- [x] confirm-cash chỉ cho PV/QL/AD; khách chọn tiền mặt → tạo StaffCall "Thanh toán tiền mặt…" + broadcast; xác nhận xong tự resolve
- [x] tests cập nhật + BrdExtraTests (gộp đơn, bảo vệ bàn, QL không cấp AD): 40/40 OK
- [x] backend/.env.example
- [x] FE Menu: xử lý order_updated / staff_call / table_updated, nút Huỷ món pending, Hóa đơn tạm tính (BillModal), làm mới menu 30s
- [x] FE PaymentModal: tiền mặt → chờ nhân viên xác nhận (poll GET /payments/{id}/)
- [x] FE Waiter: Huỷ món pending, nhãn "Khách đang chờ thanh toán tiền mặt", dùng lại payment pending, sửa lint
- [x] FE: tạo src/shared/panel.module.css (thiếu → build lỗi); `vite build` OK
- [x] Create order trả 200 khi gộp: FE dùng payload chung, không cần sửa

- [x] backend/.env tạo từ .env.example; DB_PORT=5433 (PG18 — PG14 trên 5432 sai mật khẩu); `migrate` 0001–0007 OK, `check` sạch

## Đang làm
- [x] Smoke test E2E trên PostgreSQL (daphne): auth, CRUD, đặt món theo bàn + BR-02 403, thanh toán tiền mặt, báo cáo, WS table_N → new_order; eslint + vite build OK; dữ liệu test đã dọn
- [x] test_flows.py: tiền mặt, VNPay (khoá giả), WS staff/kitchen, bàn đang dọn → 51/51 OK
- [x] Thử UI Chrome: khách/phục vụ/bếp/quản lý OK; sửa font Material Symbols (index.html), chữ 'bàn 05' cứng (Chef.jsx)
- [x] Cài skill ui-ux-pro-max vào .claude/skills (đã review an toàn)
- [x] Redesign UI theo frontend/DESIGN.md:
  - [x] B1 nền tảng: src/styles/{tokens,base,ui}.css, font, Toast/MaterialIcon, các modal
  - [x] B2a Menu khách (hero ảnh, lưới thẻ ảnh, thương hiệu ABC Restaurant) + Login/PaymentResult/PaymentQuery/TableQR/NotFound/TableQRGrid
  - [x] B2b Waiter + WaiterAddItems (header tối, thẻ bàn, ảnh món)
  - [x] B2d Manager: sidebar tối thương hiệu, topbar, KPI, bảng/modal dùng ui.css (CSS 940→210)
  - [x] B2c Chef KDS (3 cột, timer, Tình trạng món)
  - [x] Phong cách mềm + chuẩn cao cấp (tokens/ui.css), ui-preview/ (styleguide.html, README, screenshots)
  - [x] B4 Chốt option A "Basil Soft" (ui-preview/options/option-a-basil-soft.html, DESIGN.md lần 5): đã căn app theo mẫu (hero cong ellipse, font Newsreader + Plus Jakarta Sans), ui-preview cập nhật → người dùng ĐÃ DUYỆT
  - [x] B3 review + dọn dẹp: api.js money() nbsp + connectSocket() tự nối lại (1s→2s→5s→10s) dùng ở Chef/Waiter/Menu/Manager; skeleton cho bảng quản lý; xoá file thừa (panel.module.css, App.css, index.css, screens/PaymentResult/); sửa tràn input datetime/file trong modal, header Menu 390px; CRUD quản lý (món, danh mục, bàn, KM, nhân viên) + luồng khách/bếp/phục vụ/tiền mặt đã thử trên Chrome, dữ liệu test đã xoá
- Hoãn: VNPay sandbox thật (người dùng chọn bỏ qua)

- [x] Redis (Docker `emenu-redis`, redis:7-alpine, :6379, restart unless-stopped): REDIS_URL trong backend/.env; round-trip group_send OK; 2 daphne (8001/8002) giao new_order xuyên tiến trình OK; test dùng InMemory (settings bỏ Redis khi argv có 'test')

## Ngoài phạm vi (theo yêu cầu)
- MoMo / ZaloPay: không tích hợp; BR-06 dùng Tiền mặt + Chuyển khoản (VNPay sandbox)

## Lệnh chạy test
```
cd backend
DJANGO_DEBUG=1 DATABASE_URL=sqlite:///test.sqlite3 venv/Scripts/python.exe manage.py test api
```

## Chạy Redis
```
docker run -d --name emenu-redis --restart unless-stopped -p 6379:6379 redis:7-alpine   # lần đầu
docker start emenu-redis                                                                 # các lần sau
# backend/.env: REDIS_URL=redis://127.0.0.1:6379/0 (bỏ trống = InMemory, chỉ 1 tiến trình)
# chạy daphne: venv/Scripts/python.exe -m daphne -p 8001 backend.asgi:application
```

## Quy ước làm việc (cho phiên sau)
- Trả lời trực tiếp, đầu ra là code; không explain / recap / summary.
- Mỗi khi hoàn thành một việc: cập nhật ngay file này (Đã làm / Đang làm / Còn lại).
- Không tích hợp MoMo, ZaloPay.
- Cài gói pip: `env -u REQUESTS_CA_BUNDLE -u CURL_CA_BUNDLE -u SSL_CERT_FILE venv/Scripts/python.exe -m pip install ...` (biến CA trỏ sai sang E:\PostgreSQL).
- Kiểm tra FE: `cd frontend && npx eslint <file> && npx vite build`.

## Nhật ký phiên
- 2026-11-24 #1: đối chiếu BRD, viết lại backend views/services, migration 0007, 37/37 test OK.
- 2026-11-24 #2: tiền mặt chỉ nhân viên xác nhận, FE huỷ món / hoá đơn / realtime, panel.module.css, 40/40 test OK, build OK.
- 2026-11-24 #3: tạo backend/.env (PG18 cổng 5433), migrate PostgreSQL 0001–0007 OK, smoke test E2E OK.
- 2026-11-24 #4: api/test_flows.py (+10 test: tiền mặt PV/QL/AD, VNPay IPN 97/04/01/99/idempotent, WS matrix + broadcast); 50/50 OK; live PG:8001 OK; Redis không có trên :6379.
- 2026-11-24 #5: bàn "cleaning" → khách đặt món bị 400 (đúng thiết kế, order_view.py:101), FE hiển thị e.message; thêm test, 51/51 OK.
- 2026-11-24 #6: thử UI trên Chrome OK, sửa icon bếp + chữ cứng.
- 2026-11-24 #7: Redis qua Docker, REDIS_URL, kiểm tra xuyên tiến trình 8001->8002 OK, test giữ InMemory, 51/51 OK.
- 2026-11-24 #8: B2c+B3 xong (xem mục redesign); ReviewModal chưa được dùng ở đâu (khách chưa có nút đánh giá); lint/build/test chạy lại.
- 2026-11-24 #9: chốt option A Basil Soft, áp vào app; chờ duyệt. Câu hỏi mở: gắn ReviewModal sau thanh toán? thay window.prompt/confirm ở Bàn bằng modal? xoá bàn id 10 (không rõ nguồn)?
- 2026-11-24 #10: người dùng duyệt giao diện A; giữ nguyên dữ liệu (không xoá bàn 10). Chưa làm (chờ yêu cầu): gắn ReviewModal, thay prompt/confirm ở Bàn.
- 2026-11-24 #11: gắn ReviewModal + thay prompt/confirm bằng modal, route /table/:tableId; thử Chrome (khách đánh giá -> quản lý thấy, sửa/xoá bàn), dữ liệu uitest_ đã xoá; eslint/build OK, 51/51 test OK.

- [x] 2026-11-25: backend/.env có khoá VNPay sandbox (mode vnpay); thêm PAYMENT_GATEWAY_MODE (vnpay|mock, mặc định mock nếu thiếu khoá), POST /api/payments/mock-callback/ (404 khi vnpay), trang FE /payment/mock, helper _settle_pending dùng chung IPN+mock; vnpay-return đã tự cập nhật (idempotent). Test 54/54, eslint+build OK. URL VNPay sandbox thật hợp lệ (vào trang chọn phương thức). Chưa thử trả thẻ NCB qua Chrome (nhiều Chrome kết nối, cần chọn). Redis Docker đang tắt -> chạy daphne với REDIS_URL= (InMemory).
- [x] VNPay sandbox thật E2E trên compose (Browser 1): đơn #20 bàn 2, 120.000đ, thẻ NCB + chấp nhận điều khoản (người dùng đồng ý) + OTP → payment-result success; DB: order completed, payment vnpay success (ORD20T261125095520d56ff4), bàn 2 → cleaning
- [x] Load test fix: psycopg3 pool (DB_POOL_MIN/MAX/TIMEOUT, CONN_MAX_AGE=0) + cache menu/categories 10s (MENU_CACHE_TTL, invalidate qua signal); 200 user lỗi 0% (trước 63%); xem docs/testing/load/README.md; test api 213/213 OK.
- [x] 2026-11-25: Chạy lại sau vá: migrate e_menu lên 0010 (30 bàn qr_token duy nhất, số bản ghi không đổi); functional 76 Pass/0 Fail/7 thủ công (sửa: Review post_save/post_delete làm mất hiệu lực cache menu -> avg_rating đúng; script TC-005 nạp M); security 48 đạt/0 không đạt/5 thông tin (trước 39/10), bandit 0H/0M/1L; WS 200/200 với token bàn (ws_load.py sửa); BE 248/248, FE 51/51, eslint 0 lỗi, vite build OK; đã dọn server/DB tạm. Chưa đụng docker/compose.
- [x] 2026-11-25: Build lại docker (UI mới duyệt): sửa backend/Dockerfile collectstatic thêm PAYMENT_GATEWAY_MODE=mock (settings DEBUG=0 đòi khoá VNPay lúc build); migrate 0010 OK, 30 bàn qr_token duy nhất, số bản ghi không đổi; web/API 200, CSP+nosniff+X-Frame OK, Chrome headless không lỗi CSP; luồng QR/session/403/WS/đặt đơn OK, login 429 ở lần 11; NUM_PROXIES=0 giữ nguyên; đơn test #21 đã huỷ.
- [x] 2026-11-25: Sửa redis TimeoutError WS (redis-py 8.2 socket_timeout mặc định ngắn vs brpop 5s của channels_redis 4.3.0): CHANNEL_LAYERS hosts dict socket_timeout=30, keepalive, health_check_interval=30; WS 6 phút 4 client + broadcast, log 0 lỗi; test BE OK; đơn test huỷ thêm 4 (cancelled).
- [x] 2026-11-25: QR dùng lâu dài: qr_token chỉ đổi qua 'Đổi mã QR' (test chuỗi đặt món->thanh toán->cleaning->empty), FE tự gia hạn phiên bằng k đã lưu sessionStorage, ảnh QR lưu file MEDIA_ROOT/qr theo (token, base) + PUBLIC_BASE_URL, màn In QR chọn bàn + thẻ A4 + PNG/PDF/zip (qr-png/qr-pdf/qr-zip); test BE 274/274, FE 59/59, eslint/build OK; ui-preview 11-13 chờ duyệt; chưa rebuild docker (cần để ra bản mới + đặt PUBLIC_BASE_URL).
- [x] 2026-11-25: requirements.txt ghim theo venv (Django 6.1.1, DRF 3.18.1, channels 4.3.2, channels-redis 4.3.0, daphne 4.2.3, redis 8.2.0, psycopg 3.3.9, uvicorn[standard] 0.54.0...); /api/orders/ có ?page (20/100) + ?active=1 + serializer gọn (FE ManagerOrders phân trang, Waiter/Chef ?active=1); backend Dockerfile/Procfile/compose chạy uvicorn --workers ${WEB_CONCURRENCY:-3} (chưa rebuild docker); load 200 user: p95 6200->1300 ms, 40->97 RPS, lỗi 0 (docs/testing/load/README.md); test BE 249/249, FE 51/51, eslint/build OK.
