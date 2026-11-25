# Security test — ABC Restaurant

Phạm vi: chỉ backend thử nghiệm local của dự án (daphne cổng 8030 chế độ `mock`, `DJANGO_DEBUG=0`; cổng 8031 chế độ `vnpay` với khoá GIẢ để kiểm tra IPN/mock-callback; cùng DB riêng `e_menu_load`, đã xoá sau khi quét). Không tấn công hệ thống ngoài. Quét lần 2 (sau vá): throttle THẬT (không override), `NUM_PROXIES=0`, `SECURE_HSTS_SECONDS=31536000`, `PAYMENT_GATEWAY_MODE=mock` rõ ràng, `VNPAY_TMN_CODE_FAKE` khớp khoá giả của server 8031; DB `e_menu_load` đã DROP, server đã tắt.

Chạy lại: `backend/venv/Scripts/python.exe docs/testing/security/security_scan.py --base http://127.0.0.1:8030 --base-vnpay http://127.0.0.1:8031 --secret <SECRET_KEY server thử> --vnpay-secret <khoá vnpay giả>` (xem docstring).
Đầu ra: `results.json`, `results.md`, `terminal.txt`. Ảnh: `screenshots/scan_1_sqli_xss_authz.png`, `screenshots/scan_2_config_payment_rate.png`.

## Tổng hợp
Trước vá: **54** kiểm tra, **39 đạt**, **10 không đạt**, 5 thông tin. Sau vá (quét lại 2026-11-25): **53** kiểm tra, **48 đạt**, **0 không đạt**, 5 thông tin.

### Trước -> sau vá
| Mức độ | Mã | Vấn đề | Trước | Sau | Cách vá / ghi chú |
|---|---|---|---|---|---|
| Cao | RATE-01 | Brute-force login (giả X-Forwarded-For) | Không đạt | Đạt | `NUM_PROXIES` (mặc định 0): không tin X-Forwarded-For; 25 lần giả IP -> 429. Trên Railway đặt `NUM_PROXIES=1` |
| Trung bình | AUTH-05 | IDOR giả mạo header bàn | Không đạt | Đạt | `Table.qr_token` + link QR `?k=` + token phiên bàn ký `X-Table-Token`; X-Table-Id / token rác / ký sai khoá / dò k -> 403 |
| Trung bình | WS-02 | WebSocket IDOR (kênh bàn) | Không đạt | Đạt | `/ws/table_<id>/?token=`; không token / rác / token bàn khác bị từ chối |
| Trung bình | SEC-02 | `.env` có thể bị commit | Không đạt | Đạt | `.gitignore` gốc |
| Trung bình | RATE-03 | Giới hạn API khách | Không đạt | Đạt | Throttle theo bàn: order_create, staff_call, review, table_session, customer -> 429 khi vượt |
| Thấp | SQLI-01 / SQLI-05 / CFG-05 | Tham số sai kiểu gây 500 | Không đạt | Đạt | Validate kiểu -> 400 |
| Thấp | XSS-06 | Browsable API bật ở production | Không đạt | Đạt | JSONRenderer khi DEBUG=0 |
| Thấp | CFG-13 | HSTS / CSP | Không đạt | Đạt (có ghi chú) | HSTS chỉ có ý nghĩa khi chạy HTTPS: server quét đặt `SECURE_HSTS_SECONDS=31536000` thì header có `max-age=31536000` (mặc định bật khi có `RAILWAY_PUBLIC_DOMAIN`). CSP không nằm ở backend: cấu hình tĩnh ở `frontend/nginx.conf` (default-src 'self', script-src 'self', object-src 'none', frame-ancestors 'none'...), kiểm bằng đọc file, chưa kiểm qua nginx chạy thật (chờ compose) |
| Thông tin | PAY-02 | mock-callback ở chế độ mock | Thông tin | Thông tin | DEBUG=0 không còn tự rơi về mock khi thiếu khoá; production bắt buộc `PAYMENT_GATEWAY_MODE=vnpay` |

Ghi chú lần quét 2: PAY-04 ban đầu "không đạt" do script test dùng mã terminal giả khác server (lỗi cấu hình test, `RspCode 99 Invalid terminal`), đã khớp bằng biến `VNPAY_TMN_CODE_FAKE` rồi quét lại -> đạt (04). `security_scan.py` còn sửa lỗi `ws_checks` thiếu `table_token`/`cust` (truyền tham số). XSS-02: tạo danh mục tên chứa payload trả 400 (trên DB mới) nhưng món vẫn 201 và JSON trả text, vẫn đạt.

Mục còn ở mức thông tin (không sửa): AUTH-06 id tuần tự, XSS-08 JWT trong localStorage, SEC-05 `.env` dev DEBUG=1, CFG-07 `/admin/` công khai, PAY-02.


## Công cụ tĩnh
| Công cụ | Lệnh | Kết quả |
|---|---|---|
| bandit | `bandit -r backend/api --exclude tests` (2 472 dòng, lần quét 2) | 0 High, 0 Medium, 1 Low: B105 `serializers.py:236` (dương tính giả — chuỗi thông báo "Cần nhập mật khẩu..."). Chi tiết `bandit.txt`/`bandit.json` |
| pip-audit | `pip-audit -r requirements.txt` | Không có lỗ hổng đã biết (42 gói) — `pip-audit.json` |
| npm audit | `npm audit --omit=dev` (frontend) | `found 0 vulnerabilities` — `npm-audit.txt` |

## Bảng kiểm tra chi tiết
Cột "Mức độ" chỉ điền cho mục không đạt (mức nguy cơ nếu lỗi bị khai thác); "Thông tin" = ghi nhận, không tính đạt/không đạt.

| Mã | Loại lỗ hổng | Payload / cách thử | Kết quả mong đợi | Thực tế | Đạt/Không đạt | Mức độ | Khuyến nghị |
|---|---|---|---|---|---|---|---|
| SQLI-01 | SQL Injection | 18 tham số x 6 payload (q, search, date_from, table_id, order_id, category, ...) | Không 500, không lộ dữ liệu/SQL error | Sạch | Đạt | - | - |
| SQLI-02 | SQL Injection (UNION) | GET /api/menu-items/?search=' UNION SELECT username,password,... FROM api_useraccount-- | 200 danh sách rỗng, không lộ hash | HTTP 200, 0 bản ghi, lộ hash: False | Đạt | - | - |
| SQLI-03 | SQL Injection (login) | username=' OR 1=1--, admin'--; password=' OR '1'='1 | 401/400, không 200/500 | mã trả về: [401] | Đạt | - | - |
| SQLI-04 | SQL Injection (path id) | GET /api/orders\|menu-items\|tables\|payments/<1 OR 1=1 \| 1' \| UNION...>/ | 404 (không khớp route), không 500 | mã: [404] | Đạt | - | - |
| SQLI-05 | SQL Injection (body JSON) | table_id/menu_item_id/rating/order_id/code = '1 OR 1=1', note='); DROP TABLE... | 400/403/404, không 500 | [400, 400, 200, 400, 400, 400, 400] | Đạt | - | - |
| SQLI-06 | SQL Injection (DROP) | Sau mọi payload DROP TABLE, bảng api_order còn hoạt động | GET đơn vẫn 200 | HTTP 200 | Đạt | - | - |
| XSS-01 | XSS lưu trữ (ghi chú món) | <script>alert(1)</script> \| "><img src=x onerror=alert(1)> | Lưu dạng text, API trả application/json (không render HTML) | POST [200, 200, 200]; lưu raw=True; Content-Type=application/json | Đạt | - | - |
| XSS-02 | XSS lưu trữ (tên/mô tả món, tên danh mục) | name=<script>alert(1)</script> description="><img src=x onerror=alert(1)> category.name="><img src=x onerror=alert(1)> | API trả JSON text | tạo danh mục 400, món 201; Content-Type=application/json | Đạt | - | - |
| XSS-03 | XSS lưu trữ (nhận xét đánh giá) | comment="><img src=x onerror=alert(1)> | Lưu text, trả JSON | POST /reviews/ -> 201; body={"id":3,"order_item":44,"menu_item":2,"menu_item_name":"Chả  | Đạt | - | - |
| XSS-04 | XSS lưu trữ (gọi nhân viên) | message=<script>alert(1)</script> | Lưu text, trả JSON | HTTP 201; CT=application/json | Đạt | - | - |
| XSS-05 | XSS phản chiếu (Browsable API) | GET /api/menu-items/ Accept: text/html chứa tên món <script> | HTML escape (&lt;script&gt;) hoặc không có Browsable API | HTTP 406, CT=application/json, script thô trong HTML=False, browsable=False | Đạt | - | - |
| XSS-07 | XSS DOM (frontend) | grep dangerouslySetInnerHTML / innerHTML / eval / document.write trong frontend/src | Không có | Không thấy | Đạt | - | - |
| XSS-08 | Lưu JWT ở localStorage | frontend/src/services/api.js dùng localStorage cho access/refresh token | Token trong cookie HttpOnly (khuyến nghị) | Token trong localStorage — nếu có XSS thì bị đánh cắp | Thông tin | Thấp | Giữ CSP chặt; cân nhắc cookie HttpOnly+SameSite hoặc access token sống ngắn. |
| AUTH-01 | Truy cập không token | 17 endpoint quản trị/nhân viên không Authorization | 401/403 | sai: không | Đạt | - | - |
| AUTH-02 | Token role thấp (PV/BEP) | Phục vụ & Bếp gọi API chỉ QL/AD (users, reports, audit-logs, payments, tạo danh mục/món/bàn/khuyến mãi, refund) | 403 | sai: không | Đạt | - | - |
| AUTH-03 | Token Bếp ngoài vai trò | Bếp: list staff-calls, xác nhận tiền mặt, đổi trạng thái đơn | 403 | {'BEP GET /staff-calls/': 403, 'BEP confirm-cash': 403, 'BEP PATCH order status': 403} | Đạt | - | - |
| AUTH-04 | IDOR khách bàn A -> bàn B | Header X-Table-Id: 1 truy cập đơn/thanh toán/gọi NV/khuyến mãi/huỷ món của bàn 2 | 403 cho mọi thao tác | sai: không; chi tiết {'order other table': 403, 'order no header': 403, 'add-items other': 403, 'create order other table': 403, 'apply-promo other': 403, 'cancel item other': 403, 'staff-call other': 403, 'payment create other': 403, 'payment detail other': 403, 'payment sync other': 403, 'reviews list other': 0} | Đạt | - | - |
| AUTH-05 | IDOR giả mạo header bàn | Kẻ tấn công tự gửi X-Table-Id: 2 / X-Table-Token rác / token ký sai khoá / dò mã k, rồi GET /api/orders/2/ và POST thanh toán | 403 (cần token phiên bàn ký, lấy bằng mã k bí mật trong QR) | mã trả về [403, 403, 403, 403, 403] | Đạt | - | - |
| AUTH-06 | ID tuần tự dễ đoán | Đơn/bàn/thanh toán dùng id số nguyên tăng dần | Khó đoán (UUID) hoặc có kiểm soát truy cập chặt | đơn 0..2: [403, 200] | Thông tin | Thấp | Dùng mã đơn ngẫu nhiên (UUID/slug) hiển thị cho khách. |
| AUTH-07 | Leo thang vai trò | PV PATCH /users/<mình> {role:AD}; PV gửi is_superuser; QL tự nâng AD; QL tạo user AD; QL tạo user kèm is_superuser | 403/400, không tạo được AD/superuser | PV->AD 403, PV superuser 403, QL tự->AD 400, QL tạo AD 400, QL tạo is_superuser 201 | Đạt | - | - |
| AUTH-08 | Mật khẩu yếu | Tạo nhân viên với password=1234 | 400 (validator) | HTTP 400 | Đạt | - | - |
| AUTH-09 | Lộ hash mật khẩu qua API | GET /api/users/ chứa trường password/hash | Không có | có "password" trong JSON: False | Đạt | - | - |
| AUTH-10 | JWT giả/hết hạn/alg none | sai khoá, alg=none, sửa role giữ chữ ký, hết hạn, user không tồn tại, refresh làm access | Tất cả 401 (đối chứng 200) | {'sai khoá HS256': 401, 'alg none': 401, 'sửa payload giữ chữ ký': 401, 'rỗng chữ ký': 401, 'rác': 401, 'hết hạn (đúng khoá)': 401, 'hợp lệ đúng khoá (đối chứng)': 200, 'user_id không tồn tại': 401, 'token_type=refresh làm access': 401, 'refresh làm access': 401} | Đạt | - | - |
| AUTH-11 | Refresh token xoay vòng | Dùng lại refresh token cũ sau khi đã xoay | 401 (blacklist) | lần 1 có access=True, lần 2 -> 401 | Đạt | - | - |
| WS-01 | WebSocket phân quyền | Kết nối ws/kitchen_orders/, ws/staff_orders/ không token / token giả | Bị đóng (4403) | {'kitchen không token': 'từ chối (InvalidStatus)', 'staff không token': 'từ chối (InvalidStatus)', 'kitchen token giả': 'từ chối (InvalidStatus)'} | Đạt | - | - |
| WS-02 | WebSocket IDOR (kênh bàn) | Kết nối ws/table_2/ không token / token rác / token bàn 1 rồi bàn 2 đặt món; đối chứng token đúng bàn 2 | Chỉ token đúng bàn được vào; không nhận dữ liệu đơn bàn khác | {'table_2 không token': 'từ chối (InvalidStatus)', 'table_2 token rác': 'từ chối (InvalidStatus)', 'table_2 token bàn 1': 'từ chối (InvalidStatus)', 'table_2 token đúng': 'MỞ'}; nhận new_order của bàn 2 khi chưa xác thực: False | Đạt | - | - |
| BIZ-01 | Thao túng giá/mass assignment | POST /orders/ kèm unit_price=1, total_amount=1, status=completed | Server bỏ qua, tính theo giá menu | tổng=150000.0 (kỳ vọng 150000.0); status=pending | Đạt | - | - |
| BIZ-02 | Số lượng không hợp lệ | quantity = 0, -5, 1000 | 400 | [400, 400, 400] | Đạt | - | - |
| BIZ-03 | Đánh giá ngoài khoảng | rating=99 | 400 | HTTP 400 | Đạt | - | - |
| SEC-01 | Lộ bí mật trong frontend | Tìm giá trị thật của DB_PASSWORD, DJANGO_SECRET_KEY, VNPAY_HASH_SECRET_KEY, VNPAY_TMN_CODE + tên VNPAY_HASH_SECRET/DJANGO_SECRET_KEY trong frontend/dist, src, public (71 file) | Không có | Không thấy | Đạt | - | - |
| SEC-02 | backend/.env bị đóng gói/commit | Kiểm tra .gitignore / .dockerignore có loại .env | Có ở .gitignore và backend/.dockerignore | {'.gitignore': True, 'backend/.gitignore': None, 'backend/.dockerignore': True, 'frontend/.dockerignore': True, '.dockerignore': None} | Đạt | - | - |
| SEC-03 | Path traversal lấy .env / mã nguồn | GET /media/../.env, /media/%2e%2e/.env, /static/../.env, /media/../db.sqlite3 ... | 404, không trả file | Không lộ | Đạt | - | - |
| SEC-04 | SECRET_KEY mặc định/yếu | settings: DEBUG=0 mà SECRET_KEY = _DEV_KEY => ImproperlyConfigured; so sánh khoá trong .env với khoá dev | Khoá riêng, >= 50 ký tự, fail-closed khi DEBUG=0 | fail-closed khi DEBUG=0: True; .env dùng khoá dev: False; độ dài khoá .env: 50 | Đạt | - | - |
| SEC-05 | DEBUG bật trong .env | backend/.env: DJANGO_DEBUG | 0 khi triển khai | .env máy dev đặt DJANGO_DEBUG=1 (chấp nhận khi chạy local; server quét chạy DEBUG=0) | Thông tin | Thấp | Không dùng .env dev cho production. |
| CFG-04 | Lộ stacktrace (DEBUG) | Gây 404/400/lỗi tham số, đọc nội dung lỗi | Không có stacktrace/đường dẫn file | mã [404, 400, 404, 400, 400]; lộ stacktrace=False | Đạt | - | - |
| CFG-05 | Xử lý tham số sai kiểu | GET /api/orders/?table_id=abc | 400, không phải 500 | HTTP 400 | Đạt | - | - |
| CFG-06 | Host header giả | Host: evil.example.com | 400 (ALLOWED_HOSTS) | HTTP 400 | Đạt | - | - |
| CFG-07 | Trang /admin/ | GET /admin/login/ | Không công khai hoặc có bảo vệ brute-force | HTTP 200 — trang đăng nhập admin công khai, không giới hạn thử mật khẩu | Thông tin | Thấp | Đổi đường dẫn admin / chặn theo IP / thêm django-axes; bắt buộc mật khẩu mạnh. |
| CFG-08 | Upload file độc (html/svg/php) | Tải lên image_url: shell.html, x.svg (script), shell.php (image/png), shell.php.png, real.php (PNG hợp lệ tên .php) | 400 (chỉ ảnh hợp lệ) | {'shell.html': 400, 'x.svg': 400, 'shell.php': 400, 'shell.php.png': 400, 'real.php': 400, 'poly.png': 201} | Đạt | - | - |
| CFG-09 | Polyglot ảnh + mã | PNG hợp lệ + nối <?php ... ?> / <script> (poly.png) | Phục vụ đúng image/png, nosniff, không thực thi | tải lên 201; phục vụ Content-Type=image/png; nosniff=nosniff | Đạt | - | - |
| CFG-10 | Upload quá dung lượng | PNG > 5MB | 400 | HTTP 400 | Đạt | - | - |
| CFG-11 | CORS origin lạ | Origin: http://evil.example.com / null (preflight + GET) | Không có Access-Control-Allow-Origin cho origin lạ; origin FE được phép | {'http://evil.example.com': (None, None), 'null': (None, None), 'http://localhost:5173': ('http://localhost:5173', 'true')}; GET origin lạ -> ACAO=None | Đạt | - | - |
| CFG-12 | Header bảo mật | GET /api/menu-items/ — X-Frame-Options, X-Content-Type-Options, Referrer-Policy, COOP | Có đủ | X-Frame-Options=DENY, nosniff=nosniff, Referrer-Policy=same-origin; thiếu: không | Đạt | - | - |
| CFG-13 | HSTS / HTTPS | GET với X-Forwarded-Proto: https — Strict-Transport-Security; CSP; SECURE_SSL_REDIRECT | Có HSTS + CSP khi chạy https | HSTS=max-age=31536000; CSP=None | Đạt | - | - |
| PAY-01 | mock-callback ở chế độ vnpay | POST http://127.0.0.1:8031/api/payments/mock-callback/ (server PAYMENT_GATEWAY_MODE=vnpay) | 404 | HTTP 404 | Đạt | - | - |
| PAY-02 | mock-callback ở chế độ mock | Server mock: khách không token POST /payments/mock-callback/ {txn_ref, result:success} cho giao dịch chờ thanh toán | Chỉ dùng demo; production phải tắt | HTTP 200; đơn chuyển sang "completed" mà không trả tiền (hợp lệ ở mock, NGUY HIỂM nếu lọt lên production) | Thông tin | Trung bình | Không bao giờ chạy mock ở production; thêm kiểm tra settings.DEBUG hoặc biến ALLOW_MOCK_GATEWAY=1. |
| PAY-03 | IPN chữ ký sai | GET /payments/vnpay-ipn/ với vnp_SecureHash=deadbeef, ResponseCode=00 (và thiếu chữ ký) | RspCode 97, trạng thái giao dịch không đổi | {'RspCode': '97', 'Message': 'Invalid signature'}; thiếu chữ ký {'RspCode': '97', 'Message': 'Invalid signature'}; payment sau đó=pending | Đạt | - | - |
| PAY-04 | IPN chữ ký đúng nhưng sai số tiền | IPN ký bằng khoá giả của server thử, vnp_Amount=100 (sai) | RspCode 04, không ghi nhận thanh toán | {'RspCode': '04', 'Message': 'Invalid amount'}; payment=pending | Đạt | - | - |
| PAY-05 | vnpay-return chữ ký sai | GET /payments/vnpay-return/ chữ ký giả | Không đổi trạng thái giao dịch | HTTP 302; payment=pending | Đạt | - | - |
| PAY-06 | Khách tự xác nhận tiền mặt | Khách (không token) POST /payments/<id>/confirm-cash/ | 401/403 | HTTP 401 | Đạt | - | - |
| RATE-01 | Brute-force login (giả X-Forwarded-For) | 25 lần đăng nhập sai, mỗi lần X-Forwarded-For khác nhau | 429 sau 10 lần/phút (theo IP thật) | 429 xuất hiện: True; mã: [429] | Đạt | - | - |
| RATE-02 | Giới hạn đăng nhập theo IP | 16 lần đăng nhập sai liên tiếp (không giả IP) | 429 sau 10 lần | 429: True; mã: [429] | Đạt | - | - |
| RATE-03 | Giới hạn API khách | bàn mới: 30 POST /orders/, 10 POST /staff-calls/, 140 GET current-order liên tiếp (throttle theo bàn: order_create 20/min, staff_call 6/min, customer 120/min) | 429 khi vượt | 429 — orders: True, staff-calls: True, customer: True | Đạt | - | - |

## Mục đã đạt đáng chú ý
- SQLi/XSS: ORM tham số hoá, payload `' OR 1=1--`, `UNION SELECT`, `DROP TABLE` không có tác dụng; XSS lưu dạng text trong JSON, frontend không dùng `dangerouslySetInnerHTML`/`innerHTML`.
- Phân quyền: 17 endpoint quản trị từ chối không token; PV/BEP bị 403; khách bàn A không truy cập được đơn/thanh toán bàn B (khi không giả header); không leo thang vai trò; JWT sai khoá/`alg=none`/sửa payload/hết hạn/refresh làm access đều 401; refresh token xoay vòng + blacklist.
- Bí mật: không có khoá VNPay/SECRET_KEY trong `frontend/dist|src`; không lộ `.env`/mã nguồn qua `/media`, `/static`; SECRET_KEY dev bị chặn khi DEBUG=0; không stacktrace; Host giả 400; CORS chặn origin lạ; X-Frame-Options=DENY, nosniff, Referrer-Policy.
- Upload: `.html`, `.svg`, `.php` (kể cả PNG hợp lệ tên `.php`), file >5MB đều bị từ chối.
- Thanh toán: `mock-callback` 404 ở chế độ vnpay; IPN/return sai chữ ký bị từ chối (97), đúng chữ ký sai số tiền bị 04, trạng thái giao dịch không đổi; khách không tự xác nhận tiền mặt; giá/tổng tiền do server tính.
