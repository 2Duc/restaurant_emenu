# ABC Restaurant — QR Menu

Hệ thống gọi món bằng mã QR cho nhà hàng ABC Restaurant: khách quét QR tại bàn để xem menu, gọi món, thanh toán (tiền mặt / VNPay); nhân viên phục vụ, bếp và quản lý theo dõi đơn theo thời gian thực (WebSocket).

- Backend: Django + DRF + Channels (daphne), PostgreSQL, Redis
- Frontend: React + Vite

## Yêu cầu
- Python 3.12+
- Node.js 20+ (khuyến nghị 22)
- PostgreSQL 14+ (hoặc dùng SQLite chỉ để chạy test)
- Redis (vd. Docker: `docker run -d --name emenu-redis -p 6379:6379 redis:7-alpine`); để trống `REDIS_URL` thì dùng InMemory (chỉ 1 tiến trình)
- Docker (tuỳ chọn, để chạy bằng docker compose)

## Cách nhanh nhất: Docker Compose
```
copy .env.example .env      # Linux/macOS: cp .env.example .env
# sửa .env: HOST_IP=<IP LAN của máy> (ipconfig -> IPv4 Wi-Fi/Ethernet), SEED_DEMO_PASSWORD, khoá VNPay (để trống nếu dùng mock)
docker compose up -d --build
docker compose exec backend python manage.py seed_demo      # chạy 1 lần
```
- Chỉ cần đặt `HOST_IP` trong `.env` gốc: link QR (`FRONTEND_BASE_URL`), `VITE_PUBLIC_URL`, `VITE_API_BASE_URL`, `VITE_WS_BASE_URL`, `VITE_MEDIA_BASE_URL`, `VNPAY_RETURN_URL`, `VNPAY_IPN_URL`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` đều đổi theo (localhost/127.0.0.1 vẫn được giữ). Không đặt thì mặc định `localhost`.
- Các biến `VITE_*` là build-arg (nhúng lúc build): đổi `HOST_IP` phải build lại frontend: `docker compose up -d --build frontend` (mạng đổi => IP LAN đổi => làm lại).
- Web: http://HOST_IP:FRONTEND_PORT (mặc định 8080; nếu cổng 8080 đã bị chiếm, ví dụ Apache của EDB PEM, đặt `FRONTEND_PORT=8088` trong `.env` rồi build lại) — API: http://HOST_IP:8000/api/
- Mật khẩu tài khoản demo: `SEED_DEMO_PASSWORD` trong `.env`.
- DB trong compose không map cổng ra host (tránh trùng PostgreSQL local 5432/5433); Redis trong compose không map 6379 (tránh trùng `emenu-redis`).
- Dừng: `docker compose down` (thêm `-v` để xoá dữ liệu).

### Test QR bằng điện thoại cùng Wi-Fi
1. Điện thoại và máy chạy compose cùng mạng Wi-Fi; `HOST_IP` đúng IP LAN của máy (không dùng localhost).
2. Mở firewall Windows (PowerShell chạy bằng quyền Administrator, chỉ cần làm 1 lần):
```
netsh advfirewall firewall add rule name="ABC Restaurant 8080" dir=in action=allow protocol=TCP localport=8080   # đổi thành FRONTEND_PORT nếu khác
netsh advfirewall firewall add rule name="ABC Restaurant 8000" dir=in action=allow protocol=TCP localport=8000
```
   Gỡ: `netsh advfirewall firewall delete rule name="ABC Restaurant 8080"` (tương tự 8000).
3. Đăng nhập quản lý -> trang QR bàn -> quét QR bằng điện thoại (link dạng `http://HOST_IP:8080/table/<id>`) hoặc mở thẳng link đó.
4. Thanh toán VNPay sandbox: `VNPAY_RETURN_URL` trỏ về `http://HOST_IP:8000/...` nên điện thoại cũng quay lại được trang kết quả.

## Cài đặt thủ công

### Backend
```
cd backend
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Linux/macOS: cp .env.example .env  rồi điền DJANGO_SECRET_KEY, DB_*...
python manage.py migrate
set SEED_DEMO_PASSWORD=Demo@12345   # Linux/macOS: export ...
python manage.py seed_demo
python manage.py createsuperuser    # tuỳ chọn: tài khoản quản trị (sau đó đặt role = AD trong shell/admin)
daphne -b 127.0.0.1 -p 8000 backend.asgi:application
```
Ghi chú: dùng `daphne` (không dùng `runserver`) để WebSocket hoạt động. `DJANGO_DEBUG=1` khi chạy local.
Docker/Railway chạy `uvicorn backend.asgi:application --workers ${WEB_CONCURRENCY:-3}` (nhiều tiến trình; cần `REDIS_URL` để WebSocket/cache dùng chung; tổng kết nối DB = số tiến trình x `DB_POOL_MAX`). Danh sách đơn: `GET /api/orders/?page=1&page_size=20` (phân trang), `?active=1` (chỉ đơn đang mở), không tham số = dạng đầy đủ cũ.

### Frontend
```
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # bản production -> dist/
```
Biến môi trường (tạo `frontend/.env` nếu API không ở 127.0.0.1:8000): `VITE_API_BASE_URL` (vd. `http://127.0.0.1:8000/api`), `VITE_WS_BASE_URL` (vd. `ws://127.0.0.1:8000`), `VITE_MEDIA_BASE_URL`, `VITE_PUBLIC_URL` (gốc URL dùng để tạo link QR).

## Chạy test
```
cd backend
set DJANGO_DEBUG=1 & set DATABASE_URL=sqlite:///test.sqlite3
venv\Scripts\python.exe manage.py test api
cd ..\frontend && npm run lint && npx vite build
```

## Tài khoản demo
Tạo bởi `seed_demo` khi đặt `SEED_DEMO_PASSWORD` (mật khẩu do bạn đặt):

| Tài khoản | Vai trò | Màn hình |
|---|---|---|
| `manager_demo` | Quản lý (QL) | /manager |
| `waiter_demo` | Phục vụ (PV) | /waiter |
| `kitchen_demo` | Bếp (BEP) | /chef |

Admin (AD): tạo bằng `createsuperuser` rồi đặt `role=AD`. Voucher demo: `ABC10` (giảm 10%). Seed cũng tạo 24 bàn, 5 danh mục, 8 món.

## Vai trò & URL
- Khách: `/table/:id?k=<mã QR>` (link trong mã QR; `/menu?table=<số bàn>` chỉ dùng được khi trình duyệt đã có phiên bàn) — xem menu, gọi món, gọi nhân viên, thanh toán, đánh giá
- Đăng nhập nhân viên: `/login`
- Phục vụ: `/waiter` (cũng `/staff`)
- Bếp: `/chef`
- Quản lý/Admin: `/manager` (menu, đơn, khuyến mãi, bàn + QR, báo cáo)
- Kết quả thanh toán: `/payment-result`

## QR bàn
Mỗi bàn có link `http://<domain-frontend>/table/<id>?k=<qr_token>` (ví dụ `/table/12?k=Xr3...`). `k` là mã bí mật ngẫu nhiên của bàn (`Table.qr_token`); quét QR -> frontend đổi `(id, k)` lấy token phiên bàn ký (hạn 6 giờ, lưu sessionStorage) và gửi header `X-Table-Token` cho mọi API khách; kênh WebSocket bàn dùng `?token=<token phiên bàn>`. Link thiếu/sai `k` -> màn hình báo "Không mở được bàn". Menu (đọc) vẫn công khai.
- **In lại QR**: sau khi nâng cấp, link QR cũ (`/table/<id>` không có `k`) không còn dùng được -> vào Quản lý > Bàn > "Mã QR" (hoặc nút "In") để in lại mã mới. Migration 0008-0010 tự sinh `qr_token` cho mọi bàn có sẵn (không mất dữ liệu).
- **Đổi mã QR** (quản lý/admin): nút "Đổi mã QR" ở thẻ bàn -> sinh mã mới, QR cũ và mọi phiên đang mở của bàn đó mất hiệu lực (ghi nhật ký audit `TABLE_QR_ROTATE`); in lại QR mới.
- **QR dùng lâu dài, in một lần dán bàn**: `qr_token` cố định vĩnh viễn, KHÔNG tự xoay ở bất kỳ luồng nào (đặt món, thanh toán, giải phóng/dọn bàn, sửa bàn, migrate, seed, deploy); chỉ đổi khi quản lý bấm "Đổi mã QR". Khách quét lại cùng QR bất kỳ lúc nào (sau 6 giờ, tab mới, khách mới, ngày khác) đều vào được: frontend tự đổi `k` lấy token phiên mới (k giữ trong URL/sessionStorage), phiên hết hạn giữa chừng tự gia hạn, không hiện lỗi.
- **QR in ra phụ thuộc địa chỉ trong mã** (`<địa chỉ website>/table/<id>?k=...`): dùng IP LAN cố định (DHCP reservation trên router) hoặc tên miền. Đặt `PUBLIC_BASE_URL` (backend/.env hoặc .env gốc, mặc định = `FRONTEND_BASE_URL`) là địa chỉ ổn định này; đổi `HOST_IP`/địa chỉ thì QR đã in KHÔNG còn đúng và phải in lại. Màn In QR cảnh báo khi địa chỉ đang chọn khác `PUBLIC_BASE_URL` của máy chủ.
- **Ảnh QR lưu bền**: backend sinh 1 lần và lưu `MEDIA_ROOT/qr/t<id>_<băm(token, địa chỉ)>.png`; chỉ sinh lại khi token hoặc địa chỉ đổi (file cũ của bàn được dọn). Tên file không lộ token và không công bố qua API công khai (ảnh có chứa `k`).
- **Màn In QR** (Quản lý > Bàn > "Mã QR"): chọn bàn hoặc in tất cả, thẻ dán bàn khổ A4 (2x2 thẻ/trang, `@media print`) gồm "ABC Restaurant", số bàn, QR lớn, dòng hướng dẫn quét. Tải PNG từng thẻ (`GET /api/tables/<id>/qr-png/?card=1`), PDF A4 nhiều thẻ (`GET /api/tables/qr-pdf/?ids=1,2`) và zip các thẻ (`GET /api/tables/qr-zip/?ids=1,2`); bỏ `ids` = tất cả bàn; `?base_url=` đổi địa chỉ; yêu cầu đăng nhập phục vụ/quản lý.

## Thanh toán
- Tiền mặt: khách chọn → nhân viên xác nhận tại màn hình phục vụ.
- VNPay sandbox: điền `VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET_KEY` trong `backend/.env` (và các URL return/IPN trỏ về backend công khai). Thẻ test:
  - Ngân hàng NCB, số thẻ `9704198526191432198`, tên `NGUYEN VAN A`, ngày phát hành `07/15`, OTP `123456`.
- Chế độ giả lập (không cần khoá, dùng demo/test): đặt `PAYMENT_GATEWAY_MODE=mock`.
- Production (`DJANGO_DEBUG=0`): nếu KHÔNG đặt `PAYMENT_GATEWAY_MODE` thì mặc định là `vnpay` và backend báo lỗi cấu hình khi thiếu `VNPAY_TMN_CODE`/`VNPAY_HASH_SECRET_KEY` (không tự rơi về `mock`, vì `mock-callback` cho phép ai cũng đánh dấu đơn đã thanh toán). Chỉ dùng `mock` khi đặt rõ `PAYMENT_GATEWAY_MODE=mock` (bản demo).

## Deploy
- Docker Compose: xem phần đầu (`docker-compose.yml`: db, redis, backend, frontend).
- Railway: service backend trỏ thư mục `backend/` (có `Dockerfile`, `railway.json`, `Procfile`); thêm plugin PostgreSQL (`DATABASE_URL`) và Redis (`REDIS_URL`); đặt `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `NUM_PROXIES=1` (Railway có 1 proxy; đặt đúng số proxy tin cậy để throttle lấy IP thật), `SECURE_HSTS_SECONDS` (mặc định 31536000 khi có `RAILWAY_PUBLIC_DOMAIN`, đặt 0 để tắt), `PAYMENT_GATEWAY_MODE`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `MEDIA_ROOT` (trỏ Volume), các biến VNPAY_*. Frontend: service từ `frontend/` (Dockerfile, truyền build args `VITE_*`) hoặc host tĩnh `dist/` (cần fallback SPA về index.html).

## Bảo mật (tóm tắt các biến môi trường)
- `NUM_PROXIES` (mặc định `0`): số reverse proxy tin cậy trước backend; DRF dùng để lấy IP thật cho throttle (đăng nhập 10/phút/IP). Chạy trực tiếp/compose: 0; Railway hoặc 1 nginx phía trước: 1. Đặt lớn hơn thực tế sẽ cho phép giả `X-Forwarded-For`.
- Throttle API khách (theo bàn, token đã ký): `customer` 120/phút, tạo đơn 20/phút, gọi nhân viên 6/phút, đánh giá 20/phút, đổi mã QR lấy token 30/phút/IP (chỉnh ở `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`).
- `DJANGO_DEBUG=0`: chỉ trả JSON (tắt Browsable API); `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=1`, `SECURE_SSL_REDIRECT=1` (tuỳ chọn khi HTTPS).
- Frontend nginx đặt CSP theo biến `CSP_CONNECT_SRC` (API + WebSocket) và `CSP_IMG_SRC` (ảnh món); compose đã đặt theo `HOST_IP`.
- `.gitignore` ở gốc loại `.env`, `venv`, `node_modules`, `dist`, `media`, `*.sqlite3`, token load test.

## Chuyển dữ liệu local → docker
```
# 1. dump DB local (PG18, cổng 5433); lọc dòng \restrict / transaction_timeout để restore vào PG16
pg_dump -h localhost -p 5433 -U postgres -d e_menu --no-owner --no-acl -f dump.sql
grep -v '^\restrict\|^\unrestrict\|transaction_timeout' dump.sql > dump16.sql

# 2. restore vào container db (dừng backend trước)
docker stop <project>-backend-1
docker exec <project>-db-1 psql -U postgres -d postgres -c "DROP DATABASE e_menu WITH (FORCE)" -c "CREATE DATABASE e_menu"
docker exec -i <project>-db-1 psql -U postgres -d e_menu -v ON_ERROR_STOP=1 < dump16.sql
docker start <project>-backend-1

# 3. ảnh món vào volume media (MEDIA_ROOT=/data/media)
docker cp backend/media/. <project>-backend-1:/data/media/

# 4. xoá dump (chứa hash mật khẩu)
```
Không chạy `seed_demo` sau restore nếu không cần: lệnh này thêm danh mục/món demo vào dữ liệu thật.
