# UI preview - ABC Restaurant

Bản xem trước giao diện (phong cách: Basil & Tangerine, mềm, nhà hàng cao cấp).

## Nội dung
- `styleguide.html` - trang tĩnh: thương hiệu, bảng màu (kèm tỉ lệ tương phản), chữ, nút, form, badge/chip/tab, thẻ món, vé bếp, thanh giỏ hàng, card/bảng, modal, empty, toast.
- `screenshots/` - ảnh chụp màn hình (menu khách, đăng nhập, styleguide) ở độ rộng desktop.

## Cách mở
Bấm đúp `styleguide.html` (file://). Trang nạp CSS từ `../frontend/src/styles/` nên giữ nguyên cấu trúc thư mục; cần internet để tải font Google.

## Bảng màu chính
| token | giá trị | dùng cho |
|---|---|---|
| --brand | #12805A | CTA, link, focus |
| --brand-deep | #0C5A40 | wordmark, chữ xanh đậm |
| --ink-bar | #16302A | nền hero, toast |
| --accent | #F29B38 | chấm, số giỏ, gạch active (rất ít) |
| --price | #0C6648 | giá, chữ nhấn nhỏ |
| --gold | #CDB57A | đường kẻ mảnh, monogram, số danh mục |
| --bg / --surface | #F4FBF7 / #FFFFFF | nền / thẻ |
| --ink / --ink-2 | #16302A / #46605A | chữ chính / phụ |

## Cổng thanh toán giả lập (PAYMENT_GATEWAY_MODE=mock)
- Route `/payment/mock?txn=...&amount=...` (frontend/src/screens/MockGateway): 2 nút "Thanh toán thành công" / "Huỷ giao dịch" -> POST /api/payments/mock-callback/ -> chuyển sang /payment-result.
- Ảnh: `screenshots/06-payment-mock-gateway.png`, `screenshots/07-payment-result-after-mock.png`.

## Bảo mật QR bàn (AUTH-05) - giao diện mới, chờ duyệt
- Màn "Không mở được bàn" (khi link QR thiếu/sai mã `k` hoặc đã bị đổi mã): `screenshots/08-table-access-error-desktop.png`, `screenshots/09-table-access-error-mobile.png` (ảnh headless Chrome rộng tối thiểu 500px). Dùng lại khối `.empty` của hệ thống, icon `qr_code_scanner`, chữ mới.
- Nút "Đổi mã QR" ở thẻ bàn (Quản lý > Bàn), nằm cạnh "Mã QR" / "Sửa" / "Xoá"; bấm -> hộp xác nhận (ConfirmDialog, kiểu nguy hiểm) rồi thông báo "Đã đổi mã QR bàn N. Hãy in lại mã QR mới...": `screenshots/10-manager-tables-rotate-qr.png`. Hàng nút của thẻ cho phép xuống dòng (flex-wrap) để vừa 4 nút.
- Không đổi chữ/nhãn có sẵn; chỉ thêm chữ cho tính năng mới.

## Màn In QR (thẻ dán bàn) - chờ duyệt
- `screenshots/11-qr-print-screen.png`: màn In QR (chọn bàn, cảnh báo địa chỉ khác máy chủ, nút In / Tải PDF A4 / Tải tất cả zip, Tải PNG từng bàn); trang tĩnh nguồn `qr-print-preview.html` (QR trong `qr-assets/`).
- `screenshots/12-qr-the-ban-png.png`: thẻ dán bàn (file PNG tải về); `screenshots/13-qr-a4-4-the.png`: 1 trang PDF A4 (2x2 thẻ), cũng là bố cục khi in.
- Chỉ thêm chữ mới cho tính năng mới; chữ có sẵn giữ nguyên. Theo Basil Soft (brand #12805A, gold #CDB57A, Plus Jakarta Sans).

## Chuyển khoản ngân hàng + Cấu hình hệ thống (BR-06) - chờ duyệt
- Khách, hộp thanh toán: thêm lựa chọn "Chuyển khoản ngân hàng" (giữ nguyên 2 lựa chọn cũ; phương thức bị Admin tắt thì ẩn; chưa cấu hình tài khoản nhận thì ẩn lựa chọn mới): `screenshots/13-payment-modal-chon-phuong-thuc.png`.
- Màn chuyển khoản: ảnh VietQR (backend sinh), ngân hàng / số TK / chủ TK / nội dung = DON<mã đơn>, dòng "Đang chờ nhân viên xác nhận…": `screenshots/14-payment-modal-chuyen-khoan-ngan-hang.png`.
- Phục vụ: thẻ đơn có banner "Khách đang chờ xác nhận chuyển khoản" + nút "Xác nhận đã nhận chuyển khoản" (gọi /payments/<id>/confirm-manual/): `screenshots/15-waiter-xac-nhan-chuyen-khoan.png`.
- Quản lý > "Cấu hình hệ thống" (chỉ Admin; route /manager/settings): bật/tắt phương thức, tài khoản nhận, chống spam gọi nhân viên, ghi chú hoá đơn, trạng thái cổng thanh toán chỉ đọc (TMN che bớt): `screenshots/16-manager-cau-hinh-he-thong.png` (desktop), `screenshots/17-manager-cau-hinh-he-thong-mobile.png`.
- Dùng token/lớp sẵn có (card, field, badge, alert, modal); chỉ thêm chữ cho tính năng mới.
