# Unit Test — ABC Restaurant

Kết quả chạy ngày 2026-11-25. Tất cả PASS.

| Phần | Số test mới | Kết quả |
|---|---|---|
| Backend (`backend/api/tests_unit/`) | 157 | 157/157 PASS |
| Backend toàn bộ (`api`: 55 tích hợp + 157 unit) | 212 | 212/212 PASS |
| Frontend (vitest, `src/**/*.test.*`) | 41 | 41/41 PASS |

## Lệnh chạy

```bash
# Backend (từ thư mục backend/)
DJANGO_DEBUG=1 DATABASE_URL=sqlite:///test.sqlite3 venv/Scripts/python.exe manage.py test api.tests_unit -v 2   # chỉ unit
DJANGO_DEBUG=1 DATABASE_URL=sqlite:///test.sqlite3 venv/Scripts/python.exe manage.py test api -v 2             # toàn bộ

# Backend + coverage
env -u REQUESTS_CA_BUNDLE -u CURL_CA_BUNDLE -u SSL_CERT_FILE venv/Scripts/python.exe -m pip install coverage
DJANGO_DEBUG=1 DATABASE_URL=sqlite:///test.sqlite3 venv/Scripts/python.exe -m coverage run manage.py test api
venv/Scripts/python.exe -m coverage report
venv/Scripts/python.exe -m coverage html -d ../docs/testing/unit/coverage-backend-html

# Frontend (từ thư mục frontend/)
npm test                 # vitest run
npm run test:coverage    # vitest run --coverage (v8)
```

Cấu hình coverage backend: `backend/.coveragerc` (bỏ migrations và file test). Cấu hình vitest: `frontend/vite.config.js` (jsdom, setup `src/test/setup.js`).

## Coverage

### Backend (coverage.py, `coverage run manage.py test api`) — TOTAL 88% (1635 câu lệnh, 191 chưa phủ)

| Module | Cover |
|---|---|
| services/audit.py, orders.py, qr_service.py, realtime.py, scope.py, vnpay_services.py | 100% |
| permissions.py, middleware.py, urls.py, admin.py, user_view.py | 100% |
| models.py | 99% |
| serializers.py | 99% |
| views/report_view.py, review_view.py, auth_view.py | 96%, 96%, 95% |
| views/menu_view.py, table_view.py, payment_view.py | 93%, 85%, 88% |
| views/promotion_view.py, order_view.py | 81%, 80% |
| views/staff_call_view.py | 51% (chưa có unit riêng) |
| management/commands/seed_*.py | 0% (lệnh seed dữ liệu, không test) |

Báo cáo HTML: `coverage-backend-html/index.html`.

### Frontend (vitest + @vitest/coverage-v8; phạm vi: services/api.js, Menu/cartUtils.js, ConfirmDialog)

| File | Stmts | Branch | Funcs | Lines |
|---|---|---|---|---|
| Tổng | 96.52% | 85.85% | 92.72% | 95.23% |
| services/api.js | 95% | 86.36% | 84% | 93.75% |
| screens/Menu/cartUtils.js | 100% | 91.66% | 100% | 100% |
| components/ConfirmDialog (ConfirmDialog.jsx + useConfirm.jsx) | 100% | 80.95% | 100% | 100% |

Báo cáo HTML: `coverage-frontend-html/index.html`.

## Ảnh chụp kết quả (`screenshots/`)

- `backend-unit-pass-1.png`, `backend-unit-pass-2.png` — 157 unit test backend (verbosity 2)
- `backend-all-pass-1..3.png` — toàn bộ 212 test backend (55 tích hợp + 157 unit)
- `backend-coverage.png` — `coverage report`
- `frontend-vitest-pass.png` — 41 test vitest
- `frontend-coverage.png` — `vitest run --coverage`

Log gốc: `logs/`.

## Ghi chú

- Hàm thuần của trang Menu (lọc món, thêm/đổi số lượng giỏ, tổng) được tách sang `frontend/src/screens/Menu/cartUtils.js`; `Menu.jsx` gọi lại các hàm này, hành vi và giao diện không đổi.
- `compute_discount` không kiểm tra hạn / kích hoạt của mã (chỉ tính tiền); việc đó nằm ở tầng view. Test `test_compute_discount_does_not_check_validity_window` ghi nhận hành vi này.
- Test trùng tên danh mục (không phân biệt hoa thường) dùng tên ASCII vì SQLite `iexact` không so khớp hoa/thường với ký tự Unicode (PostgreSQL thì có).

## Danh sách test backend

| Module | Test | Kịch bản | Kết quả |
|---|---|---|---|
| `test_audit_service` | `AuditMixinTests.test_destroy_deletes_and_logs_with_old_label` | perform_destroy xoá đối tượng và ghi tên cũ + id cũ. | PASS |
| `test_audit_service` | `AuditMixinTests.test_update_logs_changed_fields_without_password` | perform_update liệt kê trường đã đổi, loại 'password'. | PASS |
| `test_audit_service` | `LogActionTests.test_anonymous_is_logged_as_anonymous` | Chưa đăng nhập -> actor None, tên 'anonymous'. | PASS |
| `test_audit_service` | `LogActionTests.test_custom_mode` | Tham số mode được lưu vào acted_mode. | PASS |
| `test_audit_service` | `LogActionTests.test_logs_authenticated_actor` | User đăng nhập -> ghi actor và actor_name. | PASS |
| `test_audit_service` | `LogActionTests.test_request_without_user_attribute` | Request không có thuộc tính user vẫn ghi được. | PASS |
| `test_audit_service` | `LogActionTests.test_title_truncated_to_255_and_payload_default` | Tiêu đề dài bị cắt 255; payload mặc định {}. | PASS |
| `test_models` | `OtherModelTests.test_category_ordering_by_sort_order_then_name` | Danh mục sắp theo sort_order rồi tên. | PASS |
| `test_models` | `OtherModelTests.test_invalid_status_rejected_by_full_clean` | Trạng thái ngoài choices bị full_clean từ chối. | PASS |
| `test_models` | `OtherModelTests.test_order_defaults_and_str` | Đơn mới: pending, tổng 0; __str__ có id bàn. | PASS |
| `test_models` | `OtherModelTests.test_payment_status_is_success_helper` | payment_status_is_success đúng với success/refunded, sai với failed/chưa có. | PASS |
| `test_models` | `OtherModelTests.test_status_choices_cover_expected_values` | Tập trạng thái hợp lệ của Order/OrderItem/StaffCall/Table. | PASS |
| `test_models` | `OtherModelTests.test_user_role_default_waiter_and_staffcall_str` | User mới mặc định role PV; StaffCall.__str__ có trạng thái. | PASS |
| `test_models` | `ReviewModelTests.test_one_review_per_order_item` | Mỗi dòng món chỉ 1 đánh giá (OneToOne). | PASS |
| `test_models` | `ReviewModelTests.test_rating_out_of_range_invalid` | Rating 0, 6, 100 bị từ chối bởi validator. | PASS |
| `test_models` | `ReviewModelTests.test_rating_range_1_to_5_valid` | Rating 1..5 hợp lệ. | PASS |
| `test_models` | `TableModelTests.test_defaults_and_str` | Mặc định: capacity 4, status empty; __str__ = 'Bàn <id>'. | PASS |
| `test_models` | `TableModelTests.test_numbers_unique_across_tables` | Nhiều bàn có number khác nhau. | PASS |
| `test_models` | `TableModelTests.test_resave_keeps_number` | Lưu lại bàn không đổi number. | PASS |
| `test_models` | `TableModelTests.test_save_assigns_number_equal_to_pk` | Tạo bàn -> number = id (cả trong DB). | PASS |
| `test_models` | `TableModelTests.test_save_overrides_manual_number` | Gán number tuỳ ý vẫn bị ghi đè bằng id. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_compute_discount_does_not_check_validity_window` | compute_discount chỉ tính tiền; kiểm tra hạn/kích hoạt nằm ở tầng view (ghi nhận hành vi hiện tại). | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_fixed_discount_is_returned_as_is` | Mã cố định 50k trên đơn 300k -> giảm đúng 50k. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_fixed_discount_never_exceeds_order_total` | Mã cố định 500k lớn hơn tổng 300k -> chỉ giảm 300k. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_hundred_percent_discount_equals_base` | Mã 100% -> giảm đúng bằng tổng. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_item_fixed_promotion_capped_by_item_base` | Mã cố định 150k gắn món Trà (100k) -> giảm tối đa 100k. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_item_promotion_only_counts_matching_lines` | Mã gắn món Phở 50% -> chỉ tính trên 200k của Phở, giảm 100k. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_item_promotion_without_matching_line_is_zero` | Mã gắn món không có trong đơn -> giảm 0. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_no_promotion_gives_zero_discount` | Không có mã -> giảm 0. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_percent_discount_applies_to_whole_order` | Mã 10% trên đơn 300k -> giảm 30k. | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_percent_discount_is_rounded_to_whole_vnd` | Kết quả giảm làm tròn về đồng (không có phần thập phân). | PASS |
| `test_orders_service` | `ComputeDiscountTests.test_percent_over_100_is_capped_at_base` | Dữ liệu sai 150% vẫn bị chặn ở mức tổng tiền. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_caps_fixed_discount_and_total_never_negative` | Mã cố định lớn hơn tổng -> tổng = 0, không âm. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_empty_order_is_zero` | Đơn không còn món -> mọi số tiền bằng 0. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_ignores_non_pending_payment` | Thanh toán đã thành công không bị đổi số tiền. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_keeps_vnpay_link_when_amount_unchanged` | Số tiền không đổi -> giữ nguyên link VNPay. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_recomputes_percent_after_item_removed` | Xoá dòng Trà, mã 10% được tính lại trên 200k -> giảm 20k, tổng 180k. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_resets_vnpay_link_when_amount_changes` | Thanh toán VNPay chờ: đổi số tiền -> xoá link/ngày tạo cũ để buộc tạo link mới. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_sets_subtotal_and_total_without_promotion` | Không mã: tạm tính = tổng = 300k, giảm 0. | PASS |
| `test_orders_service` | `RecalcOrderTests.test_recalc_updates_pending_cash_payment_amount` | Thanh toán chờ (tiền mặt) được cập nhật số tiền mới. | PASS |
| `test_orders_service` | `ReleaseTableTests.test_completed_and_cancelled_orders_do_not_hold_table` | Đơn completed/cancelled không giữ bàn. | PASS |
| `test_orders_service` | `ReleaseTableTests.test_custom_status_cleaning_after_payment` | Truyền status='cleaning' -> bàn chuyển sang đang dọn. | PASS |
| `test_orders_service` | `ReleaseTableTests.test_other_tables_orders_are_ignored` | Đơn mở của bàn khác không ảnh hưởng. | PASS |
| `test_orders_service` | `ReleaseTableTests.test_pending_and_confirmed_orders_keep_table_occupied` | Còn đơn pending/confirmed -> giữ nguyên trạng thái, trả False. | PASS |
| `test_orders_service` | `ReleaseTableTests.test_table_without_open_orders_becomes_empty` | Không còn đơn mở -> bàn về 'empty', trả True. | PASS |
| `test_permissions` | `HasRoleFunctionTests.test_no_roles_given` | Không truyền role nào -> False với user thường. | PASS |
| `test_permissions` | `HasRoleFunctionTests.test_role_in_list` | has_role đúng khi role nằm trong danh sách. | PASS |
| `test_permissions` | `HasRoleFunctionTests.test_superuser_and_anonymous` | Superuser luôn True; anonymous/None luôn False. | PASS |
| `test_permissions` | `PermissionMatrixTests.test_anonymous_denied` | Chưa đăng nhập hoặc user None -> bị chặn. | PASS |
| `test_permissions` | `PermissionMatrixTests.test_base_has_role_denies_by_default` | HasRole không khai báo allowed_roles -> chặn mọi người (trừ superuser). | PASS |
| `test_permissions` | `PermissionMatrixTests.test_each_role_against_each_permission` | Ma trận vai trò x quyền: đúng vai trò mới được qua. | PASS |
| `test_permissions` | `PermissionMatrixTests.test_superuser_passes_everything` | Superuser qua mọi quyền kể cả role lạ. | PASS |
| `test_permissions` | `PermissionMatrixTests.test_unknown_role_denied` | Role lạ không phải superuser -> bị chặn. | PASS |
| `test_qr_service` | `QrDataUriTests.test_box_size_and_border_change_image_size` | box_size lớn hơn -> ảnh lớn hơn. | PASS |
| `test_qr_service` | `QrDataUriTests.test_different_text_gives_different_image` | Hai nội dung khác nhau -> ảnh khác nhau; cùng nội dung -> giống nhau. | PASS |
| `test_qr_service` | `QrDataUriTests.test_long_text_still_encodes` | URL VNPay dài ~2000 ký tự với long_text=True vẫn sinh được ảnh. | PASS |
| `test_qr_service` | `QrDataUriTests.test_returns_png_data_uri` | Kết quả là data URI PNG decode được thành ảnh. | PASS |
| `test_qr_service` | `QrDataUriTests.test_unicode_text` | Chuỗi tiếng Việt không gây lỗi. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_item_status_includes_table_group` | item_status_updated tới bàn + nhân viên. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_menu_updated_goes_to_staff_groups_only` | menu_updated chỉ tới nhóm nhân viên. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_new_order_sent_to_staff_and_table_groups_on_commit` | Sau commit: gửi tới kitchen_orders, staff_orders và table_<id>. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_nothing_sent_before_commit` | Chưa commit thì không gọi group_send. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_order_updated_reloads_fresh_data` | order_updated đọc lại đơn từ DB tại thời điểm commit. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_staff_call_groups` | staff_call chỉ tới staff_orders và bàn đó. | PASS |
| `test_realtime_service` | `BroadcastAfterCommitTests.test_table_updated_groups` | table_updated tới staff_orders và bàn đó. | PASS |
| `test_realtime_service` | `RollbackTests.test_nothing_sent_when_transaction_rolls_back` | Giao dịch bị rollback -> sự kiện không bao giờ được gửi. | PASS |
| `test_realtime_service` | `RollbackTests.test_sent_once_when_transaction_commits` | Commit thật -> gửi đúng 1 lần, và chỉ sau khi thoát atomic. | PASS |
| `test_realtime_service` | `SendTests.test_send_calls_group_send_for_each_group` | _send gọi layer.group_send một lần cho mỗi nhóm. | PASS |
| `test_realtime_service` | `SendTests.test_send_without_layer_is_noop` | Không có channel layer -> bỏ qua, không lỗi. | PASS |
| `test_scope_service` | `CustomerTableIdTests.test_missing_header_is_none` | Không có header -> None. | PASS |
| `test_scope_service` | `CustomerTableIdTests.test_non_numeric_values_are_none` | Giá trị không phải số (abc, -1, 1.5, rỗng) -> None. | PASS |
| `test_scope_service` | `CustomerTableIdTests.test_returns_digit_string` | Header '5' hợp lệ -> '5'. | PASS |
| `test_scope_service` | `CustomerTableIdTests.test_strips_whitespace` | Header có khoảng trắng ' 7 ' -> '7'. | PASS |
| `test_scope_service` | `EnsureTableScopeTests.test_customer_matching_table_passes` | Khách đúng bàn (id int hoặc str) -> được phép. | PASS |
| `test_scope_service` | `EnsureTableScopeTests.test_customer_other_table_denied` | Khách thao tác bàn khác -> PermissionDenied. | PASS |
| `test_scope_service` | `EnsureTableScopeTests.test_customer_with_none_table_denied` | table_id None -> bị từ chối. | PASS |
| `test_scope_service` | `EnsureTableScopeTests.test_customer_without_header_denied` | Khách không gửi X-Table-Id -> bị từ chối. | PASS |
| `test_scope_service` | `EnsureTableScopeTests.test_staff_bypasses_scope` | Nhân viên không bị giới hạn bàn, kể cả khi không có header. | PASS |
| `test_scope_service` | `IsStaffTests.test_anonymous_or_unknown_role_is_not_staff` | Chưa đăng nhập, không có user hoặc role lạ -> không phải nhân viên. | PASS |
| `test_scope_service` | `IsStaffTests.test_staff_roles_are_staff` | PV, BEP, QL, AD đều là nhân viên. | PASS |
| `test_scope_service` | `IsStaffTests.test_superuser_is_staff_regardless_of_role` | Superuser luôn là nhân viên. | PASS |
| `test_serializers_accounts` | `ChangePasswordSerializerTests.test_weak_new_password_rejected` | Mật khẩu mới yếu bị chặn; mạnh thì qua. | PASS |
| `test_serializers_accounts` | `OrderAndPaymentSerializerTests.test_order_payment_fields_none_without_payment` | Đơn chưa có thanh toán -> payment_id/status/method None. | PASS |
| `test_serializers_accounts` | `OrderAndPaymentSerializerTests.test_order_payment_fields_with_payment` | Đơn có thanh toán -> hiển thị trạng thái/phương thức. | PASS |
| `test_serializers_accounts` | `OrderAndPaymentSerializerTests.test_qr_image_only_for_pending_vnpay_with_url` | qr_image chỉ có khi VNPay + pending + có pay_url. | PASS |
| `test_serializers_accounts` | `PromotionSerializerTests.test_code_charset` | Mã chứa khoảng trắng/ký tự lạ bị từ chối; '-' và '_' cho phép. | PASS |
| `test_serializers_accounts` | `PromotionSerializerTests.test_end_must_be_after_start` | Ngày kết thúc <= bắt đầu -> lỗi. | PASS |
| `test_serializers_accounts` | `PromotionSerializerTests.test_partial_update_uses_instance_values` | PATCH chỉ đổi value=150 trên mã percent hiện có -> vẫn bị chặn (>100). | PASS |
| `test_serializers_accounts` | `PromotionSerializerTests.test_valid_and_code_uppercased` | Mã hợp lệ và được viết hoa. | PASS |
| `test_serializers_accounts` | `PromotionSerializerTests.test_value_must_be_positive_and_percent_max_100` | Giá trị <= 0 sai; percent 101 sai, 100 đúng; fixed 101 đúng. | PASS |
| `test_serializers_accounts` | `ReviewSerializerTests.test_not_served_or_not_completed_rejected` | Món chưa phục vụ hoặc đơn chưa hoàn tất -> lỗi order_item. | PASS |
| `test_serializers_accounts` | `ReviewSerializerTests.test_rating_bounds` | Rating 0 và 6 sai; 1 và 5 đúng. | PASS |
| `test_serializers_accounts` | `ReviewSerializerTests.test_valid_review` | Món đã phục vụ trong đơn hoàn tất, 5 sao -> hợp lệ. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_admin_can_edit_admin_account` | AD sửa tài khoản AD -> hợp lệ. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_admin_can_grant_admin_role` | AD tạo được tài khoản AD. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_create_hashes_password_and_sets_is_staff` | create: mật khẩu băm; is_staff True cho QL/AD, False cho PV/BEP. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_manager_cannot_edit_admin_account` | QL sửa tài khoản AD -> lỗi detail. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_manager_cannot_grant_admin_role` | QL tạo tài khoản role AD -> lỗi trường role. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_new_account_requires_password` | Tạo mới không có mật khẩu -> lỗi password. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_no_request_context_cannot_grant_admin` | Không có request trong context -> không được cấp AD. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_password_not_in_output` | password là write_only, không xuất ra. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_superuser_counts_as_admin` | Superuser (role khác AD) cũng cấp được AD. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_update_changes_password_and_role_flag` | update: đổi mật khẩu và is_staff theo role mới. | PASS |
| `test_serializers_accounts` | `StaffSerializerTests.test_weak_password_rejected` | Mật khẩu yếu (quá ngắn / toàn số) bị validator Django chặn. | PASS |
| `test_serializers_catalog` | `CategorySerializerTests.test_blank_name_rejected` | Tên toàn khoảng trắng -> lỗi. | PASS |
| `test_serializers_catalog` | `CategorySerializerTests.test_duplicate_name_case_insensitive` | Trùng tên (không phân biệt hoa thường, ASCII; SQLite iexact không xử lý Unicode) -> lỗi. | PASS |
| `test_serializers_catalog` | `CategorySerializerTests.test_name_is_stripped` | Tên được cắt khoảng trắng đầu cuối. | PASS |
| `test_serializers_catalog` | `CategorySerializerTests.test_update_same_name_allowed` | Sửa chính danh mục đó giữ nguyên tên -> hợp lệ. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_empty_image_accepted` | Không gửi ảnh -> hợp lệ. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_image_exactly_5mb_accepted` | Biên: đúng 5MB vẫn hợp lệ. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_invalid_image_format_rejected` | File giả làm ảnh (nội dung không phải ảnh) -> lỗi image_url. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_negative_zero_and_non_numeric_price_rejected` | Giá âm, 0, không phải số -> lỗi trường price. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_oversize_image_rejected` | Ảnh > 5MB -> lỗi 'tối đa 5MB'. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_rating_annotations` | Không có annotation -> avg None, count 0; có thì làm tròn 1 chữ số. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_valid_png_accepted` | PNG thật nhỏ hợp lệ. | PASS |
| `test_serializers_catalog` | `MenuItemSerializerTests.test_valid_price_accepted` | Giá dương hợp lệ. | PASS |
| `test_serializers_catalog` | `OrderCreateSerializerTests.test_empty_items_rejected` | Danh sách món rỗng -> lỗi. | PASS |
| `test_serializers_catalog` | `OrderCreateSerializerTests.test_invalid_ids_rejected` | menu_item_id thiếu / không phải số / <= 0 -> lỗi. | PASS |
| `test_serializers_catalog` | `OrderCreateSerializerTests.test_normalises_values_and_note` | Ép kiểu số, quantity mặc định 1, note cắt khoảng trắng và tối đa 255. | PASS |
| `test_serializers_catalog` | `OrderCreateSerializerTests.test_quantity_bounds` | Số lượng 0, 100, -1 sai; 1 và 99 đúng. | PASS |
| `test_serializers_catalog` | `SimpleSerializerTests.test_item_status_choices` | Trạng thái món chỉ nhận 4 giá trị. | PASS |
| `test_serializers_catalog` | `SimpleSerializerTests.test_payment_create_methods` | Chỉ nhận vnpay / cash (không MoMo, ZaloPay). | PASS |
| `test_serializers_catalog` | `SimpleSerializerTests.test_payment_query_requires_one_id` | Truy vấn cần order_id hoặc payment_id. | PASS |
| `test_serializers_catalog` | `SimpleSerializerTests.test_refund_amount_min_1` | Hoàn tiền một phần phải >= 1; bỏ trống = hoàn toàn phần. | PASS |
| `test_serializers_catalog` | `SimpleSerializerTests.test_staff_call_message_trimmed` | Lời nhắn cắt khoảng trắng và tối đa 255 ký tự. | PASS |
| `test_serializers_catalog` | `TableSerializerTests.test_capacity_bounds` | Sức chứa: 0, 51, -3 sai; 1 và 50 đúng. | PASS |
| `test_serializers_catalog` | `TableSerializerTests.test_number_is_read_only` | Client không đặt được number; sau khi lưu number = id. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_bank_code_included_only_when_given` | Có bank_code -> thêm vnp_BankCode, không có thì bỏ. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_expire_is_after_create_by_given_minutes` | vnp_ExpireDate = CreateDate + expire_minutes. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_ip_truncated_to_45` | IP quá dài bị cắt còn 45 ký tự. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_large_amount` | Biên: số tiền lớn 2 tỷ -> nhân 100 không tràn. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_missing_config_raises` | Thiếu TMN code hoặc secret -> VNPayError. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_order_info_truncated_to_255` | order_info dài 300 ký tự bị cắt còn 255. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_unicode_and_special_chars_in_order_info_roundtrip` | Tiếng Việt, & và = trong order_info được mã hoá đúng và chữ ký vẫn hợp lệ. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_url_contains_amount_x100_and_valid_hash` | Số tiền nhân 100; chữ ký trong URL verify được. | PASS |
| `test_vnpay_service` | `BuildUrlTests.test_zero_amount_is_still_built` | Biên: amount=0 vẫn dựng URL (nghiệp vụ chặn ở tầng view). | PASS |
| `test_vnpay_service` | `ClientIpTests.test_defaults_to_loopback` | Không có gì -> 127.0.0.1 (cả khi REMOTE_ADDR rỗng). | PASS |
| `test_vnpay_service` | `ClientIpTests.test_falls_back_to_remote_addr` | Không có forwarded -> REMOTE_ADDR. | PASS |
| `test_vnpay_service` | `ClientIpTests.test_uses_first_forwarded_ip` | X-Forwarded-For nhiều IP -> lấy IP đầu tiên. | PASS |
| `test_vnpay_service` | `HashTests.test_encoded_pairs_sorts_drops_empty_and_quotes` | Sắp theo key, bỏ rỗng/None, quote_plus (space -> +, & -> %26). | PASS |
| `test_vnpay_service` | `HashTests.test_hmacsha512_handles_unicode` | Dữ liệu tiếng Việt được encode UTF-8 không lỗi. | PASS |
| `test_vnpay_service` | `HashTests.test_hmacsha512_matches_reference_implementation` | HMAC-SHA512 trùng kết quả thư viện chuẩn, độ dài 128 hex. | PASS |
| `test_vnpay_service` | `MerchantApiTests.test_http_error_becomes_vnpay_error` | HTTP 500 -> VNPayError. | PASS |
| `test_vnpay_service` | `MerchantApiTests.test_network_error_becomes_vnpay_error` | Lỗi mạng (RequestException/OSError/ValueError) -> VNPayError, không rò lỗi gốc. | PASS |
| `test_vnpay_service` | `MerchantApiTests.test_query_transaction_posts_signed_payload` | querydr gửi payload có chữ ký HMAC theo thứ tự trường quy định. | PASS |
| `test_vnpay_service` | `MerchantApiTests.test_refund_full_vs_partial_transaction_type` | Hoàn toàn phần = 02, một phần = 03; amount nhân 100; transaction_no rỗng -> '0'. | PASS |
| `test_vnpay_service` | `TxnRefTests.test_format_and_prefix` | Mã bắt đầu ORD<id>T, chỉ gồm chữ/số, dưới 100 ký tự. | PASS |
| `test_vnpay_service` | `TxnRefTests.test_unique_per_call` | Gọi liên tiếp 200 lần không trùng. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_accepts_querydict_like_input` | Nhận được cả QueryDict (dict(...) trả list) mà không ném lỗi. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_empty_secret_fails` | Chưa cấu hình khoá -> luôn False. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_missing_hash_fails` | Thiếu vnp_SecureHash -> False. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_secure_hash_type_and_non_vnp_params_ignored` | vnp_SecureHashType và tham số không bắt đầu bằng vnp_ không ảnh hưởng chữ ký. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_tampered_amount_fails` | Sửa số tiền sau khi ký -> False. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_uppercase_hash_passes` | Hash viết hoa vẫn hợp lệ (so sánh không phân biệt hoa thường). | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_valid_signature_passes` | Chữ ký đúng -> True. | PASS |
| `test_vnpay_service` | `VerifyResponseTests.test_wrong_secret_fails` | Khoá bí mật khác -> False. | PASS |

## Danh sách test frontend

| File | Nhóm / test | Kịch bản | Kết quả |
|---|---|---|---|
| `src/services/api.test.js` | money() > `formats integer VND with vi-VN grouping and currency sign` | Định dạng 85000 -> "85.000 ₫" | PASS |
| `src/services/api.test.js` | money() > `treats null, undefined, empty and NaN-like input as zero` | Giá trị rỗng/không hợp lệ -> 0 ₫ | PASS |
| `src/services/api.test.js` | money() > `accepts numeric strings` | Chuỗi số (Decimal từ API) vẫn được định dạng | PASS |
| `src/services/api.test.js` | role / user helpers > `getUser returns null when storage is empty or corrupt` | Không có user hoặc JSON hỏng -> null, không ném lỗi | PASS |
| `src/services/api.test.js` | role / user helpers > `getRole treats superuser as AD` | Superuser Django được coi là AD ở giao diện | PASS |
| `src/services/api.test.js` | role / user helpers > `getRole returns the role of a normal user` | User thường -> role của họ | PASS |
| `src/services/api.test.js` | role / user helpers > `clearTokens removes tokens and user` | Đăng xuất xoá toàn bộ token và user | PASS |
| `src/services/api.test.js` | request error handling > `returns parsed JSON on success` | Phản hồi 200 -> trả về payload đã parse | PASS |
| `src/services/api.test.js` | request error handling > `throws the "detail" message from the server` | Lỗi 400 có detail -> Error(message = detail) | PASS |
| `src/services/api.test.js` | request error handling > `falls back to "message" then plain text then generic message` | Thứ tự dự phòng: message -> text thuần -> thông báo chung | PASS |
| `src/services/api.test.js` | request error handling > `returns null for an empty body` | Body rỗng (204) -> null | PASS |
| `src/services/api.test.js` | request error handling > `sends X-Table-Id from /table/<id> and Bearer token` | Header bàn lấy từ URL QR, token gắn Authorization | PASS |
| `src/services/api.test.js` | request error handling > `reads legacy ?table= only on /menu and /payment-result` | Link cũ /menu?table=3 có header; trang khác thì không | PASS |
| `src/services/api.test.js` | request error handling > `sets JSON content type for body but not for FormData` | JSON có Content-Type; FormData để trình duyệt tự đặt | PASS |
| `src/services/api.test.js` | request error handling > `refreshes the token on 401 and retries once` | 401 + có refresh -> gọi refresh, lưu token mới, gọi lại | PASS |
| `src/services/api.test.js` | request error handling > `clears tokens when refresh fails` | Refresh thất bại -> xoá token, ném lỗi của request gốc | PASS |
| `src/services/api.test.js` | request error handling > `login stores tokens and user` | login lưu token + user vào localStorage | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `opens a socket for the group, including token when logged in` | URL có /ws/<group>/ và ?token= khi đã đăng nhập | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `reconnects with backoff 1s, 2s, 5s, 10s, 10s` | Mất kết nối liên tục -> thử lại sau 1s, 2s, 5s, 10s rồi giữ 10s | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `resets the backoff after a successful open` | onopen đặt lại bộ đếm -> lần mất kết nối kế tiếp chờ 1s | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `forwards messages and close events to handlers` | onMessage/onClose được gọi với dữ liệu tương ứng | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `stops reconnecting after the returned close function is called` | Gọi hàm đóng -> đóng socket, huỷ timer, không nối lại | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `cancels a pending reconnect timer on close` | Đóng khi đang chờ nối lại -> không tạo socket mới | PASS |
| `src/services/api.test.js` | connectSocket reconnect > `retries when the WebSocket constructor throws` | Constructor ném lỗi -> vẫn lên lịch thử lại | PASS |
| `src/screens/Menu/cartUtils.test.js` | filterMenuItems > `hides unavailable items` | Món hết (is_available=false) không hiển thị | PASS |
| `src/screens/Menu/cartUtils.test.js` | filterMenuItems > `filters by category id given as string` | Lọc theo danh mục (id dạng chuỗi) | PASS |
| `src/screens/Menu/cartUtils.test.js` | filterMenuItems > `searches name and description case-insensitively` | Tìm không phân biệt hoa thường, cả trong mô tả | PASS |
| `src/screens/Menu/cartUtils.test.js` | filterMenuItems > `returns empty list when nothing matches` | Không khớp -> mảng rỗng | PASS |
| `src/screens/Menu/cartUtils.test.js` | cart helpers > `addToCart adds a new line with quantity 1` | Thêm món mới -> dòng số lượng 1 | PASS |
| `src/screens/Menu/cartUtils.test.js` | cart helpers > `addToCart increments an existing line without mutating input` | Thêm món đã có -> tăng số lượng, không sửa mảng cũ | PASS |
| `src/screens/Menu/cartUtils.test.js` | cart helpers > `changeCartQty removes a line when quantity reaches 0` | Giảm về 0 -> xoá dòng | PASS |
| `src/screens/Menu/cartUtils.test.js` | cart helpers > `cartCount and cartTotal sum quantities and price*quantity` | Tổng số lượng và tổng tiền (giá dạng chuỗi Decimal) | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `renders message and default labels` | Hiển thị nội dung và nhãn mặc định | PASS |
| `src/components/ConfirmDialog/useConfirm.test.jsx` | useConfirm > `resolves true when confirmed and closes the dialog` | Xác nhận -> promise resolve true, hộp thoại đóng | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `calls onConfirm when confirm button is clicked` | Bấm xác nhận -> onConfirm, không gọi onCancel | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `calls onCancel when cancel button is clicked` | Bấm Huỷ -> onCancel | PASS |
| `src/components/ConfirmDialog/useConfirm.test.jsx` | useConfirm > `resolves false when cancelled` | Huỷ -> resolve false | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `calls onCancel on Escape key` | Nhấn Esc -> huỷ | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `focuses the confirm button so Enter confirms` | Nút xác nhận autoFocus; Enter kích hoạt xác nhận | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | ConfirmDialog > `cancels when clicking the backdrop but not the dialog body` | Bấm nền mờ -> huỷ; bấm trong hộp thoại -> không huỷ | PASS |
| `src/components/ConfirmDialog/ConfirmDialog.test.jsx` | PromptDialog > `submits entered values` | Nhập giá trị rồi Lưu -> onSubmit nhận object giá trị | PASS |
