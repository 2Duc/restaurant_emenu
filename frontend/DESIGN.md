# E-Menu — Design spec

Mục tiêu: trông như sản phẩm do studio làm cho một nhà hàng thật, không giống template AI.

## Nguyên tắc chống "AI look"
- KHÔNG: gradient tím/xanh, glassmorphism, blur nền, emoji làm icon, bóng đổ dày, bo góc 24px+ cho mọi thứ, chữ gradient, viền phát sáng, card lồng card, "hero" vô nghĩa, câu chữ marketing sáo rỗng.
- CÓ: lưới chặt, khoảng trắng có chủ đích, phân cấp chữ rõ, màu tiết chế (1 màu chủ đạo + 1 nhấn dùng ít), đường kẻ mảnh 1px thay cho bóng, số dạng tabular, căn lề nhất quán.
- Trạng thái đủ: hover, focus-visible (ring 2px), disabled, loading (skeleton, không spinner giữa màn hình nếu tránh được), empty state có câu chữ cụ thể, lỗi.
- `prefers-reduced-motion` tắt animation. Transition 150–200ms, easing `cubic-bezier(.2,.7,.2,1)`.

## Màu (CSS variables, định nghĩa ở `src/styles/tokens.css`)
| token | giá trị | dùng cho |
|---|---|---|
| --bg | #F7FAF5 | nền app khách (kèm --grad-page mint/peach nhạt ở góc) |
| --bg-staff | #F2F6F0 | nền màn nhân viên/quản lý |
| --surface | #FFFFFF | card, panel |
| --surface-2 | #EEF5EC | nền phụ, hàng hover |
| --line | #DDE8DA | đường kẻ (ưu tiên rgba(15,61,46,.06)) |
| --line-strong | #C6D6C2 | viền input |
| --ink | #13241C | chữ chính |
| --ink-2 | #4A5D52 | chữ phụ |
| --ink-3 | #7C8C82 | chữ mờ (chỉ chữ ≥14px) |
| --ink-bar | #0F3D2E | basil đậm: nền hero, toast (KHÔNG còn dùng cho header) |
| --on-bar / --on-bar-2 | #F2F7F1 / rgba(242,247,241,.72) | chữ trên nền --ink-bar |
| --bar-line / --bar-active | rgba(255,255,255,.10) / .08 | kẻ / nền active trên nền tối |
| --brand | #12805A | CTA, link, focus ring |
| --brand-hover | #0D6A49 | |
| --brand-soft | #E3F4EC | nền nhạt, mục active |
| --brand-deep | #0B5A40 | wordmark, chữ xanh đậm |
| --accent | #FF7A45 | cam tangerine, ≤5%: chấm, số đếm giỏ, gạch tab active, sao |
| --accent-soft | #FFEDE4 | nền cam nhạt |
| --accent-ink | #C2410C | GIÁ và chữ nhấn nhỏ trên nền sáng (≥4.5:1) |
| --gold | #B08D57 | vàng đồng: đường kẻ mảnh, monogram, số danh mục, nhãn |
| --ok | #15803D / soft #DCFCE7 | thành công, "sẵn sàng", "đã thanh toán" |
| --warn | #B45309 / soft #FEF3C7 | chờ, đang nấu |
| --danger | #DC2626 / soft #FEE2E2 | huỷ, lỗi (chữ trên soft dùng #B91C1C) |
| --info | #0369A1 / soft #E0F2FE | trạng thái trung tính |
| --grad-cta / --grad-cta-hover | 135deg #16A06E→#12805A / #12805A→#0D6A49 | nút chính, chip active |
| --grad-page / --grad-side | radial mint+peach / #FFF→#EEF5EC | nền trang / sidebar |
| --head-bg, --head-ink, --head-ink-2, --head-line, --head-hover, --head-shadow | rgba(255,255,255,.85), #13241C, #4A5D52, rgba(15,61,46,.06), .06, 0 4px 16px rgba(15,61,46,.06) | header sáng mờ |
| --hero-tint, --overlay | rgba(15,61,46,.62), rgba(15,61,46,.45) | lớp phủ hero, backdrop modal |
| --r-sm/md/lg/xl/pill | 10 / 14 / 18 / 24 / 999 | bo góc |
| --shadow-1, --shadow-pop | xem tokens.css | bóng mềm ám xanh |

Dark mode: không bắt buộc.

## Chữ
- UI: **Be Vietnam Pro** (400/500/600/700) — hỗ trợ tiếng Việt đầy đủ.
- Display (chỉ màn khách: tên quán, tiêu đề danh mục, tên món trong chi tiết): **Fraunces** (500/600, opsz).
- Google Fonts, subset vietnamese, `display=swap`. Icon: giữ Material Symbols Outlined (weight 400, grade 0, size 20/24), không dùng emoji.
- Thang: 12 / 13 / 14 / 16 / 18 / 22 / 28 / 36. Body 14 (staff) / 16 (khách). line-height 1.5 body, 1.2 heading. Tiêu đề letter-spacing -0.01em.
- Giá tiền, số lượng, mã đơn, giờ: `font-variant-numeric: tabular-nums`. Định dạng giá: `125.000 ₫`.

## Không gian & hình khối
- Lưới 4px. Spacing: 4 8 12 16 20 24 32 40 56.
- Bo góc: 6 (input, badge), 10 (card, button), 14 (modal, bottom sheet). Pill chỉ cho chip lọc danh mục.
- Bóng: chỉ `--shadow-1: 0 1px 2px rgba(28,25,23,.06)` và `--shadow-pop: 0 8px 24px rgba(28,25,23,.12)` cho modal/dropdown.
- Vùng chạm ≥ 44px trên mobile.

## Thành phần (class dùng chung, `src/styles/ui.css`)
- `.btn` + `.btn-primary | .btn-secondary | .btn-ghost | .btn-danger`, `.btn-sm | .btn-lg`, `.btn-block`; trạng thái loading `[aria-busy=true]`.
- `.input`, `.select`, `.textarea`, `.field` (label 13px/500 + hint + error).
- `.badge` + `.badge-ok | -warn | -danger | -info | -neutral | -brand` (chữ 12px/600, nền soft, không viền).
- `.card` (surface, viền --line, bo 10, padding 16/20).
- `.modal-backdrop`, `.modal` (desktop: giữa màn, max 520px; mobile ≤640px: bottom sheet bo trên 14px, có thanh kéo).
- `.table` (header 12px uppercase tracking .04em --ink-2, hàng 48px, kẻ ngang 1px, hover --surface-2, số căn phải).
- `.tabs`, `.chip` (lọc danh mục), `.empty` (icon 32px --ink-3 + 1 câu + action), `.skeleton`.
- `.toast` góc dưới (mobile: trên thanh giỏ hàng).

## Bố cục theo màn
- **Khách (Menu, mobile-first 375px)**: header gọn — tên quán (Fraunces) + "Bàn 05" badge + nút gọi phục vụ; thanh chip danh mục dính trên (sticky, cuộn ngang); danh sách món dạng hàng (ảnh vuông 88px bo 8 bên phải, tên 16/600, mô tả 2 dòng --ink-2, giá --brand tabular, nút "+" tròn 36px); món hết hàng: mờ 50% + badge "Hết món". Thanh giỏ hàng dính đáy: "3 món · 245.000 ₫" + nút "Xem giỏ". Trạng thái đơn: timeline dọc (Chờ xác nhận → Đang nấu → Đã phục vụ).
- **Phục vụ (Waiter, tablet 768+)**: lưới bàn — ô bàn có số bàn lớn, trạng thái bằng thanh màu trái 4px + badge, thời gian đã ngồi; panel phải chi tiết bàn. Yêu cầu gọi phục vụ: danh sách ưu tiên trên cùng, mới nhất nổi bật nền --warn-soft.
- **Bếp (Chef, màn ngang 1280+)**: kiểu KDS — cột theo trạng thái (Chờ / Đang nấu / Xong), vé đơn có số bàn lớn, đồng hồ đếm phút (≥10 phút chuyển --warn, ≥20 --danger), món + số lượng chữ to 16/600, ghi chú nền --warn-soft. Nền --bg-staff, độ tương phản cao, không trang trí.
- **Quản lý (Manager, desktop 1280+)**: sidebar trái 240px nền --surface, viền phải 1px, mục active: nền --brand-soft + chữ --brand + vạch trái 3px; topbar 56px (tiêu đề trang + hành động). Nội dung max-width 1200. Báo cáo: hàng KPI (4 ô, số 28/600 tabular, so sánh kỳ trước nhỏ bên dưới) + biểu đồ SVG đơn giản 1 màu --brand, lưới mờ. Bảng dùng `.table`.
- **Đăng nhập**: chia đôi trên desktop — trái là ảnh/khối màu --ink với tên quán + 1 dòng mô tả, phải là form 360px; mobile chỉ form.
- **Kết quả thanh toán / QR / 404**: căn giữa, icon trạng thái trong vòng tròn soft 56px, tiêu đề 22, mô tả 1 dòng, 1–2 nút.

## Lớp thương hiệu (bổ sung — BẮT BUỘC, ưu tiên hơn các mục trên nếu mâu thuẫn)
Phản hồi người dùng: bản đầu "xấu, giống công cụ nội bộ". Mọi màn phải mang cảm giác **website nhà hàng cao cấp** (tham chiếu tinh thần: trang web nhà hàng fine-dining / bistro Việt hiện đại), không phải dashboard trơn.
- **Nhận diện**: tên quán "ABC Restaurant", wordmark Fraunces 600 italic + một dấu hiệu nhỏ (monogram "ABC" trong vòng tròn viền 1px màu --accent) dùng chung qua component cục bộ hoặc SVG inline. Tagline: "Hương vị Việt, nấu mỗi ngày".
- **Thanh đầu trang tối**: mọi màn (khách, phục vụ, bếp, quản lý, đăng nhập) dùng header nền `--ink` (#1C1917), chữ #F5F0E8, wordmark bên trái, đường kẻ dưới 1px `rgba(255,255,255,.08)`. Sidebar quản lý cũng nền --ink (mục active: nền rgba(255,255,255,.06), chữ trắng, vạch trái 3px --accent).
- **Hình ảnh món là trung tâm**: ở màn khách, món có ảnh thật (image_url) hiển thị lớn — lưới thẻ 2 cột mobile / 3–4 cột desktop, ảnh tỉ lệ 4:3 bo 10, `object-fit: cover`; không có ảnh → khối --surface-2 với icon "restaurant" mờ. Ở màn phục vụ thêm món và quản lý thực đơn cũng có thumbnail 48–64px.
- **Hero màn khách**: dải đầu cao ~220px (mobile 180) nền --ink với ảnh món nổi bật làm nền (lấy món đầu tiên có ảnh, phủ lớp tối 55%), tên quán Fraunces 36/28, dòng "Bàn 05 · Khu A" và nút "Gọi phục vụ" viền sáng. Không dùng ảnh stock ngoài.
- **Tiêu đề danh mục** dạng nhà hàng: Fraunces 22–28, kèm số món nhỏ --ink-3, đường kẻ mảnh kéo dài.
- **Màu nhấn**: --accent (#FF7A45) dùng cho chi tiết thương hiệu (monogram, vạch active, sao, "Món đặc trưng"). --brand cho CTA/giá.
- **Màn bếp/phục vụ**: vẫn ưu tiên đọc nhanh nhưng phải đẹp: header tối có thương hiệu, vé/ô bàn là thẻ trắng bo 10, bóng --shadow-1, số bàn Fraunces 600, khoảng thở rộng hơn, icon Material nhỏ cạnh nhãn (timer, note, table_restaurant).
- **Đăng nhập**: nửa trái là ảnh món (từ API menu nếu lấy được không cần đăng nhập, ngược lại nền --ink với monogram lớn + tagline), nửa phải form trên nền --bg.
- Chi tiết tinh tế: chữ hoa nhỏ tracking .12em cho nhãn phụ ("THỰC ĐƠN", "ĐƠN ĐANG MỞ"), số liệu tabular, hover thẻ nâng nhẹ 2px + bóng --shadow-pop (tắt khi reduced-motion).

## Phong cách mềm (bổ sung lần 2 — ƯU TIÊN CAO NHẤT, ghi đè mọi mục trên nếu mâu thuẫn)
Phản hồi người dùng: không thích mảng màu đặc (solid) phẳng; muốn khối và đường nét mềm mại. Giữ bảng màu Basil & Tangerine.
- **Bỏ thanh tối đặc**: header khách/phục vụ/bếp/quản lý chuyển sang nền sáng (trắng 85% + backdrop-blur 12px nhẹ, chỉ cho header dính) với bóng mềm, wordmark màu --brand-deep. Sidebar quản lý: nền gradient rất nhẹ từ #FFFFFF → --surface-2 (dọc), mục active là "viên thuốc" bo 12 nền --brand-soft, chữ --brand, chấm --accent.
- **Gradient mềm được phép** (thay quy tắc cấm cũ), chỉ dạng nhạt, cùng họ màu: ví dụ nền trang `radial-gradient` mint rất nhạt ở góc; nút chính `linear-gradient(135deg, #16A06E, #12805A)`; KPI tile nền trắng có vệt màu nhạt góc. Không dùng gradient tím/xanh dương, không chữ gradient.
- **Bo góc lớn hơn**: input/badge 10, nút 12 (nút CTA chính dạng pill 999), card 18, modal/bottom sheet 24, ảnh món 14, chip pill.
- **Bóng mềm nhiều lớp, ám màu xanh**: --shadow-1 `0 1px 2px rgba(15,61,46,.04), 0 4px 12px rgba(15,61,46,.06)`; --shadow-pop `0 12px 32px rgba(15,61,46,.12)`. Card không cần viền khi đã có bóng (hoặc viền rgba rất nhạt).
- **Đường cong & hình khối hữu cơ**: hero màn khách có cạnh dưới cong (SVG wave hoặc border-radius 0 0 32px 32px), ảnh nền phủ gradient mềm từ rgba(15,61,46,.15) lên rgba(15,61,46,.7) phía dưới; trang đăng nhập và trạng thái rỗng có 1–2 "blob" SVG mờ (opacity .12–.18, màu --brand-soft/--accent-soft) làm nền trang trí. Không lạm dụng: tối đa 2 blob mỗi màn.
- **Nhịp chuyển động mềm**: hover nâng 2–3px, transition 220ms ease-out; nút nhấn scale .98. Tôn trọng reduced-motion.
- **Đường kẻ**: thay đường kẻ cứng 1px bằng khoảng trắng hoặc kẻ rgba(15,61,46,.06); bảng dùng hàng bo góc nhẹ khi hover.
- Màn bếp vẫn phải dễ đọc từ xa: giữ tương phản cao cho số bàn/tên món, chỉ làm mềm khối/bo góc/bóng.

## Chuẩn nhà hàng cao cấp (bổ sung lần 3 — áp dụng cùng "Phong cách mềm")
Tham chiếu tinh thần: Fiola, Attica, Quay, Bastible, Osteria 60 (web fine-dining): bảng màu tiết chế, chữ có chân tinh tế, khoảng trắng rộng, ảnh món kiểu editorial làm trung tâm, điểm nhấn kim loại ấm.
- **Tiết chế màu**: 80% nền sáng/trung tính, 15% xanh húng quế (--brand), ≤5% cam (--accent). Cam chỉ cho chi tiết nhỏ (chấm, số đếm giỏ, gạch chân active, sao) — KHÔNG làm nền khối lớn, KHÔNG dùng cho nút lớn. Thêm điểm nhấn **vàng đồng** --gold #B08D57 (đường kẻ trang trí mảnh, monogram, nhãn "Món đặc trưng", số thứ tự danh mục).
- **Chữ editorial**: tiêu đề Fraunces cỡ lớn, weight 500 (không đậm quá), letter-spacing -0.02em; nhãn phụ chữ hoa nhỏ tracking .16em cỡ 11–12 màu --gold hoặc --ink-3; tên món Fraunces 18–20 trên thẻ; giá đặt cạnh tên, sans-serif tabular, không in đậm chói.
- **Khoảng trắng hào phóng**: khoảng giữa các section ≥ 56px desktop / 40px mobile; padding thẻ 20–24; lưới món gap 24 desktop / 16 mobile; tối đa 3 cột thẻ món trên desktop (thoáng hơn 4).
- **Ảnh món editorial**: tỉ lệ 4:5 (dọc) hoặc 4:3 thống nhất, bo 14, hover zoom ảnh 1.04 trong khung (overflow hidden) thay vì nâng cả thẻ; filter nhẹ `saturate(1.05) contrast(1.02)` cho đồng đều.
- **Chi tiết trang trí tinh tế**: đường kẻ mảnh vàng đồng ngắn (32px) dưới tiêu đề danh mục; số thứ tự danh mục "01 — Khai vị"; dấu chấm giữa ( · ) phân tách thông tin.
- **Nút**: CTA chính pill xanh gradient mềm; nút phụ viền mảnh --line-strong nền trong suốt; không dùng nút cam lớn.
- **Thao tác đơn giản**: đường đi gọi món ngắn, giỏ hàng luôn trong tầm tay, không popup gây phiền.
- Màn nhân viên (bếp/phục vụ/quản lý) theo cùng ngôn ngữ nhưng thiên về rõ ràng: ít trang trí hơn, giữ chữ editorial cho tiêu đề và số bàn.

## CHỐT CUỐI: Option A "Basil Soft" (lần 5 — người dùng đổi ý, chọn A; GHI ĐÈ mục Noir & Bronze bên dưới)
Chuẩn tham chiếu trực quan duy nhất: `ui-preview/options/option-a-basil-soft.html`. App phải trông giống trang này (màu, font, bo góc, bóng, hero, thẻ món, chip, giỏ hàng, vé bếp, KPI, thẻ bàn).
Token gốc từ option A: page #E3EFE8, frame/ink #16302A, bg #F4FBF7, surface #FFFFFF, ink-2 #46605A, brand #12805A (chữ trắng), line #DCE9E1, gold #CDB57A, tangerine #F29B38 (chỉ chi tiết nhỏ), price #0C6648, radius 18 / 12. Font: hiển thị **Newsreader** (opsz, 500), nội dung **Plus Jakarta Sans** (400–700) — cả hai phải nạp subset vietnamese.
Mục Noir & Bronze bên dưới chỉ còn giá trị lưu trữ, KHÔNG áp dụng.

## (Lưu trữ, không áp dụng) Noir & Bronze (lần 4)
Giữ nguyên: phong cách mềm (bo góc lớn, bóng mềm, đường cong, blob tiết chế), chuẩn cao cấp (chữ editorial Fraunces, khoảng trắng rộng, số danh mục "01 —", ảnh editorial, tối đa 3 cột món), font Be Vietnam Pro + Fraunces, quy tắc không đổi nội dung chữ.
- **Nền tối ấm toàn app**: --bg #141210, --bg-staff #121110, --surface #1C1916, --surface-2 #242019, --surface-3 #2C2720 (hover/input), --line rgba(232,220,200,.08), --line-strong rgba(232,220,200,.16).
- **Chữ kem**: --ink #F3EBDD, --ink-2 #C9BEAD, --ink-3 #9A8F80 (chỉ chữ ≥14px).
- **Đồng (bronze)** là màu thương hiệu: --brand #C08A52, --brand-hover #D49B60, --brand-deep #9A6A38, --brand-soft rgba(192,138,82,.14); chữ trên nút đồng: #1A140E. CTA: pill gradient `linear-gradient(135deg,#D9A46B,#B07A43)` chữ #1A140E. Giá tiền: --price #E2B07A.
- --gold = #C9A46A (đường kẻ trang trí, số danh mục, monogram); --accent dùng chính bronze sáng #E2B07A cho bong bóng giỏ/sao (không còn cam).
- **Trạng thái (trên nền tối)**: ok #6FBF8A / soft rgba(111,191,138,.14); warn #E0A84F / soft rgba(224,168,79,.14); danger #E5735F / soft rgba(229,115,95,.14); info #7FB2D9 / soft rgba(127,178,217,.14). Badge: chữ màu đậm đủ, nền soft.
- **Header**: nền rgba(20,18,16,.72) + backdrop-blur 14px, kẻ dưới --line; wordmark Fraunces italic màu --ink, monogram viền --gold. Sidebar quản lý: --surface với gradient dọc rất nhẹ sang #181512, active = pill --brand-soft chữ --brand, chấm --gold.
- **Hero khách**: ảnh tràn viền (full-bleed), phủ `linear-gradient(180deg, rgba(20,18,16,.15) 0%, rgba(20,18,16,.85) 100%)`, cạnh dưới cong, tên quán Fraunces lớn màu kem.
- **Thẻ**: --surface, viền 1px rgba(192,138,82,.14), bóng `0 1px 0 rgba(255,255,255,.03) inset, 0 12px 32px rgba(0,0,0,.35)`; hover: viền rgba(192,138,82,.32) + glow `0 0 0 1px rgba(192,138,82,.18), 0 16px 40px rgba(0,0,0,.45)`.
- **Input**: nền --surface-2, viền --line-strong, focus viền --brand + ring rgba(192,138,82,.35).
- **Modal/bottom sheet**: --surface, backdrop rgba(0,0,0,.6) + blur 6px.
- **Bếp**: nền tối rất hợp KDS; số bàn kem 34px, timer warn/danger dùng màu trạng thái trên nền tối; ghi chú nền warn-soft chữ #F3D9A8.
- **Quản lý**: biểu đồ cột màu --brand trên lưới rgba(232,220,200,.06); bảng: header chữ --ink-3, hàng hover --surface-2.
- Ảnh món: filter nhẹ `saturate(1.05) contrast(1.04) brightness(.96)` để hoà nền tối.
- theme-color #141210; `color-scheme: dark` trên :root; scrollbar tối.
- Tương phản: chữ thường ≥4.5:1 trên --surface và --bg (kiểm tra --ink-3 chỉ dùng cho chữ lớn/nhãn phụ).

## Ràng buộc kỹ thuật
- Không đổi logic, API, state, route, tên prop. Chỉ JSX cấu trúc hiển thị + CSS.
- Giữ CSS Modules hiện có nhưng thay giá trị cứng bằng `var(--token)`; xoá CSS chết khi chắc chắn không dùng.
- Không thêm thư viện UI. Có thể thêm font qua `index.html`.
- Kiểm tra: `npx eslint src && npx vite build` sạch; xem ở 375px và 1280px.
