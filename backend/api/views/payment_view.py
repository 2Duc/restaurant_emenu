from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Order, Payment, Table
from ..models import StaffCall
from ..params import int_param
from ..permissions import IsManagerOrAdmin, IsWaiterOrManager
from ..services.audit import log_action
from ..services.orders import release_table_if_idle
from ..services.realtime import broadcast_order_updated, broadcast_staff_call
from ..services.scope import ensure_table_scope, is_staff
from ..services.system_settings import method_enabled
from ..models import SystemSetting
from ..throttles import CustomerThrottle
from .order_view import _parse_date
from ..serializers import (
    PaymentCreateSerializer, PaymentQuerySerializer, PaymentRefundSerializer, PaymentSerializer,
)
from ..services.vnpay_services import (
    VNPayError, build_vnpay_payment_url, get_client_ip, new_txn_ref, query_transaction,
    refund_transaction, verify_vnpay_response,
)

REUSE_LINK_MINUTES = 10
CASH_CALL_PREFIX = 'Thanh toán tiền mặt'
BANK_CALL_PREFIX = 'Khách chờ xác nhận chuyển khoản'


def _is_success(params) -> bool:
    return params.get('vnp_ResponseCode') == '00' and params.get('vnp_TransactionStatus') == '00'


def _finalize_payment(payment, success, vnp_params=None):
    """Hoàn tất thanh toán — idempotent, dùng chung cho return URL, IPN, sync và xác nhận tiền mặt."""
    if payment.status in (Payment.Status.SUCCESS, Payment.Status.REFUNDED):
        return
    if vnp_params:
        payment.vnp_transaction_no = str(vnp_params.get('vnp_TransactionNo', ''))[:30]
        payment.vnp_response_code = str(vnp_params.get('vnp_ResponseCode', ''))[:5]
        payment.vnp_bank_code = str(vnp_params.get('vnp_BankCode', ''))[:30]
        payment.vnp_pay_date = str(vnp_params.get('vnp_PayDate', ''))[:14]
    payment.status = Payment.Status.SUCCESS if success else Payment.Status.FAILED
    if success:
        payment.paid_at = timezone.now()
    payment.save()
    order = payment.order
    if success:
        # AC-06 / BR-11: thanh toán thành công → hoàn tất đơn, ghi nhận doanh thu, bàn chuyển sang "đang dọn".
        order.status = Order.Status.COMPLETED
        order.save(update_fields=['status', 'updated_at'])
        release_table_if_idle(order.table, Table.Status.CLEANING)   # client suy ra từ order_updated
    broadcast_order_updated(order)


def _settle_pending(payment, success, params=None) -> bool:
    """Khoá giao dịch và chốt kết quả nếu còn 'pending' — dùng chung cho IPN VNPay và cổng giả lập. True nếu vừa chốt."""
    with transaction.atomic():
        locked = Payment.objects.select_for_update().select_related('order', 'order__table').get(pk=payment.pk)
        if locked.status != Payment.Status.PENDING:
            return False
        _finalize_payment(locked, success, params)
        return True


def is_mock_mode() -> bool:
    return settings.PAYMENT_GATEWAY_MODE == 'mock'


def _can_reuse_link(payment, order) -> bool:
    if payment.method != Payment.Method.VNPAY or payment.status != Payment.Status.PENDING:
        return False
    if not payment.pay_url or int(payment.amount) != int(order.total_amount) or not payment.vnp_create_date:
        return False
    try:
        created = datetime.strptime(payment.vnp_create_date, '%Y%m%d%H%M%S')
    except ValueError:
        return False
    age = datetime.now() - created
    return timedelta(0) <= age < timedelta(minutes=REUSE_LINK_MINUTES)


class PaymentCreateAPIView(APIView):
    """POST /api/payments/create/ {order_id, method: 'vnpay' | 'cash'}

    - vnpay: tạo link VNPay + trả về mã QR (qr_image) do backend sinh.
    - cash:  tạo giao dịch ở trạng thái chờ; khách/nhân viên bấm xác nhận bằng /payments/<id>/confirm-cash/.
    """
    permission_classes = [AllowAny]
    throttle_classes = [CustomerThrottle]   # RATE-03

    @transaction.atomic
    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(Order.objects.select_for_update().select_related('table'), id=serializer.validated_data['order_id'])
        ensure_table_scope(request, order.table_id)
        method = serializer.validated_data['method']
        cfg = SystemSetting.load()
        if not method_enabled(cfg, method):
            return Response({'detail': 'Phương thức thanh toán này hiện không khả dụng.'}, status=400)
        if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
            existing = Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).first()
            if existing:
                return Response(PaymentSerializer(existing).data)
            return Response({'detail': 'Đơn hàng đã kết thúc.'}, status=400)
        if order.total_amount <= 0:
            return Response({'detail': 'Giá trị đơn hàng không hợp lệ.'}, status=400)

        payment = Payment.objects.filter(order=order).first()
        if payment and payment.status in (Payment.Status.SUCCESS, Payment.Status.REFUNDED):
            return Response(PaymentSerializer(payment).data)
        if payment and method == 'vnpay' and _can_reuse_link(payment, order):
            return Response(PaymentSerializer(payment).data)

        txn_ref = new_txn_ref(order.id)
        if payment is None:
            payment = Payment(order=order, transaction_id=txn_ref)
        payment.method = method
        payment.amount = order.total_amount
        payment.status = Payment.Status.PENDING
        payment.transaction_id = txn_ref
        payment.pay_url = ''
        payment.vnp_create_date = ''
        payment.vnp_transaction_no = payment.vnp_response_code = payment.vnp_bank_code = payment.vnp_pay_date = ''

        if method == 'vnpay' and is_mock_mode():
            payment.vnp_create_date = timezone.localtime().strftime('%Y%m%d%H%M%S')
            payment.pay_url = (f'{settings.FRONTEND_BASE_URL}/payment/mock?'
                               + urlencode({'txn': txn_ref, 'amount': int(order.total_amount), 'order': order.id, 'table': order.table_id}))
        elif method == 'vnpay':
            try:
                payment.pay_url, payment.vnp_create_date = build_vnpay_payment_url(
                    amount=int(order.total_amount), txn_ref=txn_ref,
                    order_info=f'Thanh toan don hang {order.id} ban {order.table_id}',
                    ip_addr=get_client_ip(request), bank_code=settings.VNPAY_BANK_CODE,
                )
            except VNPayError as exc:
                return Response({'detail': str(exc)}, status=503)
        payment.save()
        if method == 'cash' and not is_staff(request):
            # Khách chọn tiền mặt → báo nhân viên đến thu; chỉ nhân viên mới xác nhận đã thu (confirm-cash).
            call = StaffCall.objects.filter(table=order.table, status=StaffCall.Status.PENDING,
                                            message__startswith=CASH_CALL_PREFIX).first()
            if call is None:
                call = StaffCall.objects.create(table=order.table,
                                                message=f'Thanh toán tiền mặt đơn #{order.id}: {int(order.total_amount):,}đ'.replace(',', '.'))
                broadcast_staff_call(call)
        if method == 'bank_transfer' and not is_staff(request):
            # Khách chọn chuyển khoản ngân hàng → báo nhân viên đối chiếu & xác nhận đã nhận tiền.
            if not StaffCall.objects.filter(table=order.table, status=StaffCall.Status.PENDING,
                                            message__startswith=BANK_CALL_PREFIX).exists():
                call = StaffCall.objects.create(table=order.table,
                                                message=f'{BANK_CALL_PREFIX} đơn #{order.id}: {int(order.total_amount):,}đ'.replace(',', '.'))
                broadcast_staff_call(call)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentCashConfirmAPIView(APIView):
    """POST /api/payments/<id>/confirm-cash/ — nhân viên phục vụ / quản lý xác nhận đã thu tiền mặt."""
    permission_classes = [IsWaiterOrManager]

    @transaction.atomic
    def post(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_for_update().select_related('order', 'order__table'), pk=pk)
        if payment.method != Payment.Method.CASH:
            return Response({'detail': 'Giao dịch này không phải thanh toán tiền mặt.'}, status=400)
        if payment.status == Payment.Status.PENDING:
            if int(payment.amount) != int(payment.order.total_amount):
                return Response({'detail': 'Số tiền đơn đã thay đổi, vui lòng tạo lại yêu cầu thanh toán.'}, status=400)
            _finalize_payment(payment, True)
            StaffCall.objects.filter(table_id=payment.order.table_id, status__in=[StaffCall.Status.PENDING, StaffCall.Status.ACCEPTED],
                                     message__startswith=CASH_CALL_PREFIX).update(status=StaffCall.Status.RESOLVED, handled_by=request.user)
            log_action(request, 'PAYMENT_CASH_CONFIRM', f'Xác nhận thu tiền mặt đơn #{payment.order_id}',
                       {'payment_id': payment.pk, 'amount': int(payment.amount)}, mode='waiter')
        elif payment.status != Payment.Status.SUCCESS:
            return Response({'detail': 'Giao dịch không còn ở trạng thái chờ.'}, status=400)
        return Response(PaymentSerializer(payment).data)


class PaymentDetailAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CustomerThrottle]

    def get(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_related('order'), pk=pk)
        ensure_table_scope(request, payment.order.table_id)
        return Response(PaymentSerializer(payment).data)


class PaymentListAPIView(APIView):
    """GET /api/payments/?method=&status=&date_from=&date_to=&limit= — danh sách giao dịch (quản lý)."""
    permission_classes = [IsManagerOrAdmin]

    def get(self, request):
        p = request.query_params
        qs = Payment.objects.select_related('order').order_by('-created_at')
        if p.get('method'):
            qs = qs.filter(method=p['method'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        start, end = _parse_date(p.get('date_from')), _parse_date(p.get('date_to'), end=True)
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        limit = max(1, min(int_param(p.get('limit'), 'limit') or 500, 1000))
        return Response(PaymentSerializer(qs[:limit], many=True).data)


class PaymentSyncAPIView(APIView):
    """POST /api/payments/<id>/sync/ — hỏi VNPay (querydr) xem giao dịch chờ đã được trả chưa.

    Giúp màn hình QR tự cập nhật ngay cả khi IPN không gọi được về máy local.
    """
    permission_classes = [AllowAny]
    throttle_classes = [CustomerThrottle]

    def post(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_related('order', 'order__table'), pk=pk)
        ensure_table_scope(request, payment.order.table_id)
        sync_error = ''
        if (not is_mock_mode() and payment.method == Payment.Method.VNPAY and payment.status == Payment.Status.PENDING
                and payment.vnp_create_date):
            try:
                result = query_transaction(
                    txn_ref=payment.transaction_id, transaction_date=payment.vnp_create_date,
                    order_info=f'Tra cuu giao dich {payment.transaction_id}', ip_addr=get_client_ip(request),
                )
                if (_is_success(result) and result.get('vnp_TmnCode', settings.VNPAY_TMN_CODE) == settings.VNPAY_TMN_CODE
                        and str(result.get('vnp_Amount', '')) == str(int(payment.amount) * 100)):
                    with transaction.atomic():
                        locked = Payment.objects.select_for_update().select_related('order', 'order__table').get(pk=payment.pk)
                        _finalize_payment(locked, True, result)
                        payment = locked
            except VNPayError as exc:
                sync_error = str(exc)
        data = PaymentSerializer(payment).data
        if sync_error:
            data['sync_error'] = sync_error
        return Response(data)


class PaymentQueryAPIView(APIView):
    """POST /api/payments/query/ {order_id | payment_id} — tra cứu giao dịch (màn hình quản lý)."""
    permission_classes = [IsManagerOrAdmin]

    def post(self, request):
        serializer = PaymentQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lookup = {'pk': serializer.validated_data['payment_id']} if serializer.validated_data.get('payment_id') else {'order_id': serializer.validated_data['order_id']}
        payment = get_object_or_404(Payment.objects.select_related('order'), **lookup)
        if payment.method != Payment.Method.VNPAY or not payment.vnp_create_date:
            return Response({'payment': PaymentSerializer(payment).data, 'vnpay': None,
                             'detail': 'Giao dịch này không đi qua VNPay nên không có dữ liệu tra cứu.'})
        try:
            result = query_transaction(
                txn_ref=payment.transaction_id,
                transaction_date=payment.vnp_pay_date or payment.vnp_create_date,
                order_info=f'Tra cuu giao dich {payment.transaction_id}', ip_addr=get_client_ip(request),
            )
        except VNPayError as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'payment': PaymentSerializer(payment).data, 'vnpay': result})


class PaymentRefundAPIView(APIView):
    """POST /api/payments/refund/ {payment_id, amount?, reason?} — hoàn tiền VNPay (quản lý)."""
    permission_classes = [IsManagerOrAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = PaymentRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = get_object_or_404(Payment.objects.select_for_update().select_related('order'), pk=serializer.validated_data['payment_id'])
        if payment.method != Payment.Method.VNPAY or payment.status not in (Payment.Status.SUCCESS,):
            return Response({'detail': 'Chỉ hoàn tiền được giao dịch VNPay đã thanh toán thành công.'}, status=400)
        remaining = int(payment.amount) - int(payment.refunded_amount)
        amount = int(serializer.validated_data.get('amount') or remaining)
        if amount <= 0 or amount > remaining:
            return Response({'detail': f'Số tiền hoàn phải từ 1 đến {remaining} VND.'}, status=400)
        full_refund = amount == int(payment.amount) and int(payment.refunded_amount) == 0
        reason = serializer.validated_data.get('reason') or 'Hoan tien don hang'
        try:
            result = refund_transaction(
                txn_ref=payment.transaction_id, amount=amount,
                transaction_date=payment.vnp_pay_date or payment.vnp_create_date,
                transaction_no=payment.vnp_transaction_no, order_info=reason[:200],
                created_by=request.user.username, full_refund=full_refund, ip_addr=get_client_ip(request),
            )
        except VNPayError as exc:
            return Response({'detail': str(exc)}, status=503)
        if result.get('vnp_ResponseCode') == '00':
            payment.refunded_amount = Decimal(int(payment.refunded_amount) + amount)
            if int(payment.refunded_amount) >= int(payment.amount):
                payment.status = Payment.Status.REFUNDED
            payment.save(update_fields=['refunded_amount', 'status'])
            log_action(request, 'PAYMENT_REFUND', f'Hoàn {amount} VND cho đơn #{payment.order_id}',
                       {'payment_id': payment.pk, 'amount': amount, 'reason': reason[:200]})
        return Response({'payment': PaymentSerializer(payment).data, 'vnpay': result})


class VNPayReturnAPIView(APIView):
    """Trình duyệt của khách được VNPay chuyển về đây; backend xác thực rồi redirect sang trang kết quả React."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        params = request.GET.dict()
        valid = verify_vnpay_response(params)
        payment = Payment.objects.filter(transaction_id=params.get('vnp_TxnRef', ''), method='vnpay').select_related('order', 'order__table').first()
        result = 'invalid'
        if valid and payment:
            try:
                amount = int(params.get('vnp_Amount', '0'))
            except (TypeError, ValueError):
                amount = 0
            if amount == int(payment.amount) * 100 and params.get('vnp_TmnCode') == settings.VNPAY_TMN_CODE:
                success = _is_success(params)
                with transaction.atomic():
                    locked = Payment.objects.select_for_update().select_related('order', 'order__table').get(pk=payment.pk)
                    if locked.status == Payment.Status.SUCCESS:
                        result = 'success'
                    else:
                        _finalize_payment(locked, success, params)
                        result = 'success' if success else 'failed'
        order_id = payment.order_id if payment else ''
        table_id = payment.order.table_id if payment else ''
        return redirect(f'{settings.FRONTEND_RETURN_URL}?status={result}&order={order_id}&table={table_id}')


class VNPayIPNAPIView(APIView):
    """VNPay gọi server-to-server để báo kết quả (cần URL public, đăng ký trong cấu hình merchant sandbox)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        params = request.GET.dict()
        if not verify_vnpay_response(params):
            return Response({'RspCode': '97', 'Message': 'Invalid signature'})
        if params.get('vnp_TmnCode') != settings.VNPAY_TMN_CODE:
            return Response({'RspCode': '99', 'Message': 'Invalid terminal'})
        payment = Payment.objects.filter(transaction_id=params.get('vnp_TxnRef', ''), method='vnpay').first()
        if not payment:
            return Response({'RspCode': '01', 'Message': 'Order not found'})
        try:
            amount = int(params.get('vnp_Amount', '0'))
        except (TypeError, ValueError):
            return Response({'RspCode': '04', 'Message': 'Invalid amount'})
        if amount != int(payment.amount) * 100:
            return Response({'RspCode': '04', 'Message': 'Invalid amount'})
        if not _settle_pending(payment, _is_success(params), params):
            return Response({'RspCode': '02', 'Message': 'Order already confirmed'})
        return Response({'RspCode': '00', 'Message': 'Confirm Success'})


class MockGatewayCallbackAPIView(APIView):
    """POST /api/payments/mock-callback/ {txn_ref, result: 'success' | 'cancel'} — cổng giả lập, chỉ khi PAYMENT_GATEWAY_MODE=mock."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if not is_mock_mode():
            raise Http404
        txn_ref = str(request.data.get('txn_ref', ''))
        result = request.data.get('result')
        if result not in ('success', 'cancel'):
            return Response({'detail': 'result phải là success hoặc cancel.'}, status=400)
        payment = get_object_or_404(Payment.objects.select_related('order'), transaction_id=txn_ref, method=Payment.Method.VNPAY)
        success = result == 'success'
        applied = _settle_pending(payment, success, {
            'vnp_TransactionNo': f'MOCK{payment.pk:08d}', 'vnp_ResponseCode': '00' if success else '24',
            'vnp_BankCode': 'MOCK', 'vnp_PayDate': timezone.localtime().strftime('%Y%m%d%H%M%S'),
        })
        if applied:
            log_action(request, 'PAYMENT_MOCK_' + ('SUCCESS' if success else 'CANCEL'),
                       f'Cổng giả lập: {"thanh toán thành công" if success else "huỷ giao dịch"} đơn #{payment.order_id}',
                       {'payment_id': payment.pk, 'amount': int(payment.amount)}, mode='system')
        payment.refresh_from_db()
        return Response({'status': 'success' if payment.status == Payment.Status.SUCCESS else 'failed',
                         'applied': applied, 'payment': PaymentSerializer(payment).data})


class PaymentManualConfirmAPIView(APIView):
    """POST /api/payments/<id>/confirm-manual/ — PV/QL/AD xác nhận đã nhận tiền (tiền mặt hoặc chuyển khoản ngân hàng)."""
    permission_classes = [IsWaiterOrManager]

    @transaction.atomic
    def post(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_for_update().select_related('order', 'order__table'), pk=pk)
        if payment.method not in (Payment.Method.CASH, Payment.Method.BANK_TRANSFER):
            return Response({'detail': 'Giao dịch này không phải thanh toán thủ công (tiền mặt / chuyển khoản ngân hàng).'}, status=400)
        is_bank = payment.method == Payment.Method.BANK_TRANSFER
        if payment.status == Payment.Status.PENDING:
            if int(payment.amount) != int(payment.order.total_amount):
                return Response({'detail': 'Số tiền đơn đã thay đổi, vui lòng tạo lại yêu cầu thanh toán.'}, status=400)
            _finalize_payment(payment, True)
            StaffCall.objects.filter(table_id=payment.order.table_id, status__in=[StaffCall.Status.PENDING, StaffCall.Status.ACCEPTED],
                                     message__startswith=BANK_CALL_PREFIX if is_bank else CASH_CALL_PREFIX
                                     ).update(status=StaffCall.Status.RESOLVED, handled_by=request.user)
            log_action(request, 'PAYMENT_BANK_CONFIRM' if is_bank else 'PAYMENT_CASH_CONFIRM',
                       f'Xác nhận đã nhận chuyển khoản đơn #{payment.order_id}' if is_bank else f'Xác nhận thu tiền mặt đơn #{payment.order_id}',
                       {'payment_id': payment.pk, 'amount': int(payment.amount), 'method': payment.method}, mode='waiter')
        elif payment.status != Payment.Status.SUCCESS:
            return Response({'detail': 'Giao dịch không còn ở trạng thái chờ.'}, status=400)
        return Response(PaymentSerializer(payment).data)
