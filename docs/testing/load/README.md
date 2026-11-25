# Load test — ABC Restaurant (Locust)

## Môi trường
| Mục | Giá trị |
|---|---|
| Máy | Windows 11, 12 luồng CPU, backend + PostgreSQL + Locust cùng một máy (kết quả tuyệt đối thấp hơn môi trường thật) |
| Backend | Django 6.1 + DRF + Channels, `daphne -b 127.0.0.1 -p 8030 backend.asgi:application` (1 tiến trình), `DJANGO_DEBUG=0` |
| CSDL | PostgreSQL 18 cổng 5433, database riêng `e_menu_load` (`max_connections=100`); `CONN_MAX_AGE=60` (mặc định của dự án) |
| Channel layer | InMemory (`REDIS_URL=` rỗng) |
| Dữ liệu | `migrate` + `seed_demo` + `seed_tables_promos` (30 bàn, 8 món, 6 khuyến mãi, tài khoản demo) |
| Công cụ | Locust 2.47.0, headless, mỗi mức chạy 100 giây (mức 20: 60 giây) |
| Throttle | Nhân viên dùng JWT tạo sẵn (`make_tokens.py`) nên không bị throttle đăng nhập 10/phút (nếu dùng đăng nhập thật thì 429 hàng loạt vì cùng IP; đặt `LOGIN_REAL=1` để đo). Không tắt throttle trong code. API khách không có throttle. |

## Kịch bản (`locustfile.py`)
| Loại user | Tỉ lệ | Hành vi (wait 1–3 giây) |
|---|---|---|
| `CustomerUser` (khách tại bàn, header `X-Table-Id`) | 16/20 | GET menu-items, categories (trọng số 5), GET tables/<id> (2), POST orders theo bàn (3), GET orders/<id> (3), POST staff-calls (1) |
| `WaiterKitchenUser` | 3/20 | JWT PV hoặc BEP; list orders, list staff-calls, chuyển trạng thái món pending→cooking→done→served |
| `ManagerUser` | 1/20 | JWT QL; GET reports/summary, list orders |

Chạy lại:
```
cd backend
venv/Scripts/python.exe ../docs/testing/load/make_tokens.py ../docs/testing/load/tokens.json   # cùng biến môi trường DB với server
TOKENS_FILE=../docs/testing/load/tokens.json venv/Scripts/python.exe -m locust -f ../docs/testing/load/locustfile.py \
  --headless -u 200 -r 20 -t 100s --host http://127.0.0.1:8030 --csv out --html out.html
venv/Scripts/python.exe ../docs/testing/load/ws_load.py --host 127.0.0.1:8030 --n 200 --hold 15     # WebSocket
```

## Kết quả HTTP (tổng hợp mọi endpoint)
| User đồng thời | Spawn rate | Số request | Lỗi | Tỉ lệ lỗi | RPS | RPS thành công | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 5/s | 628 | 0 | 0% | 10.8 | 10.8 | 110 | 290 | 410 |
| 50 | 10/s | 2 439 | 153 | 6.3% | 24.9 | 23.4 | 270 | 800 | 1 500 |
| 100 | 20/s | 3 156 | 2 101 | 66.6% | 32.2 | 10.8 | 1 000 | 2 700 | 3 200 |
| 200 | 20/s | 3 299 | 2 091 | 63.4% | 33.4 | 12.2 | 3 300 | 7 800 | 8 700 |
| 200 (thử nghiệm `CONN_MAX_AGE=0`, `settings_load_tuned.py`) | 20/s | 1 914 | 202 | 10.6% | 19.5 | 17.4 | 7 800 | 11 000 | 13 000 |

Toàn bộ lỗi là HTTP 500 `psycopg2.OperationalError: FATAL: sorry, too many clients already` (log daphne), không có lỗi nghiệp vụ. Số liệu theo từng endpoint: `results/u*_stats.csv`; báo cáo HTML: `results/u*.html`.

Ảnh báo cáo: `screenshots/locust_u50.png`, `locust_u100.png`, `locust_u200.png`, `locust_u200_connmax0.png`.

## Kết quả SAU khi tối ưu (connection pool psycopg3 + cache menu)
Thay đổi: `psycopg[binary,pool]` (thay psycopg2), `DATABASES.OPTIONS.pool` (`DB_POOL_MIN=2`, `DB_POOL_MAX=10`, `DB_POOL_TIMEOUT=30`; `DB_POOL_MAX=0` tắt pool), `CONN_MAX_AGE=0`; cache 10 giây (`MENU_CACHE_TTL`) cho GET `menu-items`/`categories` của khách, tự vô hiệu khi thêm/sửa/xoá món/danh mục (signal) và khi bật/tắt bán. Cùng máy, 1 tiến trình daphne, DB `e_menu_load` mới (đã DROP).
Lưu ý: từ phiên bảo mật, khách phải có `X-Table-Token` (`make_tokens.py` tạo sẵn) và có throttle theo bàn/IP; để đo năng lực DB, chạy server với `DJANGO_SETTINGS_MODULE=settings_load_nothrottle` (PYTHONPATH trỏ tới thư mục này; không đổi code ứng dụng).

| User đồng thời | Lỗi trước | Lỗi sau | RPS trước -> sau | p50 trước -> sau (ms) | p95 trước -> sau (ms) | p99 trước -> sau (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0% | 0% (0/693) | 10.8 -> 11.8 | 110 -> 16 | 290 -> 48 | 410 -> 71 |
| 50 | 6.3% | 0% (0/2 977) | 23.4 -> 30.2 | 270 -> 38 | 800 -> 170 | 1 500 -> 280 |
| 100 | 66.6% | 0% (0/4 409) | 10.8 -> 44.6 | 1 000 -> 550 | 2 700 -> 1 400 | 3 200 -> 1 800 |
| 200 | 63.4% | 0% (0/3 978) | 12.2 -> 40.3 | 3 300 -> 3 500 | 7 800 -> 6 200 | 8 700 -> 7 200 |

Không còn lỗi 500 / `too many clients` (sau tải chỉ còn 10 kết nối tới `e_menu_load`, đúng bằng `DB_POOL_MAX`). Ở 100-200 user độ trễ tăng do 1 tiến trình bão hoà (hàng đợi luồng): `GET /api/orders/` trả ~530 KB/lần (200 đơn lồng items) và chạy ~3 lần/s là phần nặng nhất. Ảnh: `screenshots/locust_after_u50.png`, `locust_after_u100.png`, `locust_after_u200.png`; số liệu: `results/after_u*_stats.csv`.

Đề xuất vận hành (chưa đo): chạy 2-4 tiến trình daphne sau nginx/Railway replicas (tổng kết nối = số tiến trình x `DB_POOL_MAX`, giữ < `max_connections`), đặt `REDIS_URL` để chia sẻ cache + channel layer; phân trang `GET /orders/` để giảm payload.

## Kết quả SAU phân trang + danh sách đơn gọn + nhiều worker (2026-11-25)
Thay đổi: `GET /api/orders/` thêm `?page=N&page_size<=100` (mặc định 20, dạng `{count,next,previous,results}`) và `?active=1` (chỉ đơn đang mở), cả hai dùng serializer gọn (bỏ `created_by`, ảnh/tên danh mục/`order` của từng món); không tham số giữ dạng đầy đủ cũ. FE: Quản lý dùng phân trang, PV/Bếp dùng `?active=1`. Backend chạy `uvicorn --workers N` (compose: `WEB_CONCURRENCY`, mặc định 3).
Môi trường: máy riêng như trên (cùng máy với PG), DB tạm `e_menu_load` (PG 18, cổng 5433, đã DROP; 300 đơn completed seed sẵn, `psycopg3 pool` max 10/tiến trình), **Redis `emenu-redis` :6379 (db 15)** cho channel layer + cache, uvicorn cổng 8030, `settings_load_nothrottle`, Locust 100 giây/mức, `LIST_MODE=old|new` trong `locustfile.py` (old = cách gọi FE cũ `/orders/?limit=200`; new = `?active=1` cho PV/Bếp, `?page=1&page_size=20` cho quản lý). Mỗi mức chạy trên DB đã cắt về 300 đơn.

| Cấu hình | User | Request | Lỗi | RPS | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| TRƯỚC: 1 worker, list đầy đủ | 100 | 3 263 | 1 (ConnectionReset) | 33.0 | 1 200 | 2 400 | 6 000 |
| TRƯỚC: 1 worker, list đầy đủ | 200 | 3 737 | 1 | 37.8 | 4 000 | 6 300 | 6 600 |
| 1 worker, list gọn/phân trang | 100 | 5 037 | 1 | 51.0 | 260 | 890 | 1 200 |
| 1 worker, list gọn/phân trang | 200 | 5 913 | 1 | 59.9 | 1 400 | 4 200 | 4 700 |
| 3 worker + Redis, list gọn/phân trang | 100 | 5 096 | 0 | 51.7 | 43 | 240 | 14 000 (*) |
| 3 worker + Redis, list gọn/phân trang | 200 | 9 549 | 0 | 96.8 | 210 | 1 300 | 2 000 |

(*) p99 100 user của cấu hình 3 worker bị kéo bởi vài request đầu lúc 3 tiến trình khởi động/nạp pool; p95 240 ms. Lỗi 0 `too many clients` ở mọi mức (3 worker x pool 10 = 30 kết nối).
Dung lượng `GET /api/orders/` (trung bình): ~300 KB (list cũ, limit 200) -> 65-170 KB (danh sách gọn; con số tăng theo số đơn mở/số dòng món do bài đo liên tục tạo đơn, mỗi bàn gộp nhiều món). So với 200 user trước đó (1 worker, kết quả mục "SAU khi tối ưu pooling": p95 6 200 ms, 40.3 RPS): 3 worker đạt p95 1 300 ms, 96.8 RPS.
Ảnh: `screenshots/locust_v2_old1_u200.png`, `locust_v2_new1_u200.png`, `locust_v2_new3_u100.png`, `locust_v2_new3_u200.png`; số liệu `results/v2_*`. Ghi chú: lần đầu chạy 3 worker trên Windows, tiến trình con mồ côi từ lượt trước còn giữ cổng 8030 nên đã chạy lại riêng cấu hình 3 worker sau khi dọn sạch tiến trình; DB tạm đã DROP, server 8030 đã tắt.

## Kết quả WebSocket (`ws_load.py`, kênh `/ws/table_<id>/`)
| Kết nối đồng thời | Thành công | Bắt tay p50 / p95 (ms) | Ping→pong p50 / p95 (ms) | Broadcast `new_order` tới người nghe cùng bàn p95 (ms) |
|---:|---:|---:|---:|---:|
| 50 | 50/50 | 209 / 228 | 38 / 41 | 273 |
| 200 | 200/200 | 646 / 729 | 116 / 143 | 402 |

WebSocket chịu được 200 kết nối đồng thời, không rớt kết nối (lúc không có tải HTTP).

## Nhận xét điểm nghẽn
1. **Cạn kết nối PostgreSQL** (nguyên nhân chính). Với ASGI, Django chạy mỗi request đồng bộ trong một luồng riêng (`ThreadSensitiveContext`), mỗi luồng giữ một kết nối DB; `CONN_MAX_AGE=60` khiến kết nối không được đóng khi luồng kết thúc. Quan sát: sau khi tải xong vẫn còn ~33 kết nối `idle` thuộc `e_menu_load`; ở 100+ user vượt `max_connections=100` nên >60% request trả 500. Đây là mốc sập "cứng", không phải chậm dần.
2. **Độ trễ nền cao**: ngay cả 20 user, GET categories p50 ~110 ms; do mỗi request mở kết nối PG mới (xác thực SCRAM) thay vì tái sử dụng. Thông lượng thành công tối đa ~24 RPS (mức 50 user), vượt 50 user là suy giảm.
3. Đặt `CONN_MAX_AGE=0` giảm lỗi (63% → 10.6%) nhưng làm chậm hơn (p95 11 s) vì mở/đóng kết nối mỗi request — không phải lời giải.
4. Endpoint nặng nhất theo kích thước: `GET /api/orders/` (~64–85 KB/lần, serializer lồng items); `reports/summary` tải toàn bộ payment vào bộ nhớ (xem `report_view.py`).
5. Cổng khách không có rate limit (cấu hình `customer: 120/min` chưa gắn vào view) nên tải dồn từ một nguồn không bị chặn.
6. Redis không dùng trong bài đo (InMemory); hành vi nhiều tiến trình chưa được đo.

## Khuyến nghị (bản gốc trước tối ưu; pooling và cache menu đã áp dụng, xem mục "SAU")
- Dùng connection pooling: psycopg3 + `DATABASES['default']['OPTIONS']['pool']=True` (Django ≥ 5.1) hoặc PgBouncer (transaction mode); đặt `CONN_MAX_AGE=0` khi dùng pooler ngoài.
- Chạy nhiều worker (gunicorn + `uvicorn.workers.UvicornWorker`, hoặc nhiều tiến trình daphne sau nginx) cùng Redis channel layer; tính tổng kết nối = số worker × luồng.
- Cache ngắn (5–30 giây) cho `GET /menu-items/`, `/categories/` (dữ liệu gần như tĩnh, chiếm ~50% lưu lượng khách); `ETag`.
- Phân trang `GET /orders/` (hiện limit mặc định 200, trả ~80 KB) và dùng `SUM/GROUP BY` trong `reports/summary`.
- Gắn throttle cho POST của khách (`orders`, `staff-calls`, `payments/create`).
- Đo lại sau khi pool với 200–500 user trên máy riêng, kèm Redis.

## Dọn dẹp
Đã `DROP DATABASE e_menu_load`, tắt daphne cổng 8030/8031, xoá `tokens.json`. DB `e_menu` không bị đụng.

## Cập nhật WebSocket sau vá (2026-11-25)
`ws_load.py` dùng token bàn (`/ws/table_<id>/?token=`, lấy từ `tokens.json` do `make_tokens.py` tạo, khoá `TABLES`; đơn kích hoạt gửi kèm `X-Table-Token`) thay cho `X-Table-Id`. Chạy nhanh 200 kết nối (hold 10s, daphne 8030, DB tạm `e_menu_load` đã DROP): 200/200 kết nối, 0 lỗi, connect p50 368 ms / p95 386 ms, ping p50 30 ms / p95 36 ms, 7 client bàn 1 nhận `new_order` (p95 135 ms).
