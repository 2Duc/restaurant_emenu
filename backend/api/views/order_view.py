from datetime import datetime, time

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import MenuItem, Order, OrderItem, Payment, Table
from ..params import int_param
from ..permissions import IsStaffMember, IsWaiterOrManager, has_role
from ..serializers import OrderCreateSerializer, OrderItemSerializer, OrderItemStatusSerializer, OrderListSerializer, OrderSerializer
from ..services.orders import OPEN_STATUSES, recalc_order, release_table_if_idle
from ..services.realtime import broadcast_item_status, broadcast_new_order, broadcast_order_updated, broadcast_table_updated
from ..services.scope import ensure_table_scope, is_staff
from ..throttles import CustomerThrottle, OrderCreateThrottle

# BR-03: Chờ chế biến → Đang chế biến → Đã hoàn thành → Đã phục vụ
ITEM_TRANSITIONS = {'pending': {'cooking'}, 'cooking': {'done'}, 'done': {'served'}, 'served': set()}
ORDER_TRANSITIONS = {'pending': {'confirmed', 'cancelled'}, 'confirmed': {'cancelled', 'completed'}}


def _parse_date(value, end=False):
    try:
        d = datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(datetime.combine(d, time.max if end else time.min))


def _build_items(order, items_data):
    lines = []
    for item in items_data:
        menu_item = get_object_or_404(MenuItem, id=item['menu_item_id'], is_available=True)
        lines.append(OrderItem(order=order, menu_item=menu_item, quantity=item['quantity'],
                               note=item.get('note', ''), unit_price=menu_item.price, status=OrderItem.Status.PENDING))
    OrderItem.objects.bulk_create(lines)


class OrderPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _lite(request):
    """Danh sách gọn khi có ?page hoặc ?active=1; còn lại giữ dạng đầy đủ cũ."""
    p = request.query_params
    return 'page' in p or p.get('active') in ('1', 'true')


def _order_qs():
    return Order.objects.select_related('table', 'promotion', 'payment').prefetch_related('items__menu_item__category')


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    POST   /api/orders/                    → khách / nhân viên tạo đơn (BR-01, BR-02)
    GET    /api/orders/                    → danh sách cho nhân viên (lọc status, table_id, q, date_from, date_to, limit;
                                           ?active=1 chỉ đơn đang mở, gọn; ?page=N[&page_size<=100] phân trang, gọn)
    GET    /api/orders/{id}/               → chi tiết / hoá đơn tạm tính
    PATCH  /api/orders/{id}/status/        → nhân viên / quản lý cập nhật trạng thái đơn
    POST   /api/orders/{id}/add-items/     → gọi thêm món
    """
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ('create', 'retrieve', 'add_items'):
            return [AllowAny()]
        if self.action == 'update_status':
            return [IsWaiterOrManager()]
        return [IsStaffMember()]

    def get_throttles(self):   # RATE-03
        if self.action == 'create':
            return [OrderCreateThrottle(), CustomerThrottle()]
        if self.action in ('retrieve', 'add_items'):
            return [CustomerThrottle()]
        return []

    def get_queryset(self):
        qs = _order_qs()
        if self.action != 'list':
            return qs
        p = self.request.query_params
        if _lite(self.request):
            qs = Order.objects.select_related('table', 'promotion', 'payment').prefetch_related('items__menu_item')
        if p.get('active') in ('1', 'true'):
            qs = qs.filter(status__in=OPEN_STATUSES)
        table_id = int_param(p.get('table_id'), 'table_id')
        if table_id is not None:
            qs = qs.filter(table_id=table_id)
        if p.get('status'):
            qs = qs.filter(status__in=p['status'].split(','))
        if p.get('q'):
            q = p['q'].strip().lstrip('#')
            qs = qs.filter(Q(pk=q) | Q(table__number=q)) if q.isdigit() else qs.filter(table__area__icontains=q)
        start, end = _parse_date(p.get('date_from')), _parse_date(p.get('date_to'), end=True)
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        if 'page' in request.query_params:
            paginator = OrderPagination()
            page = paginator.paginate_queryset(self.get_queryset(), request, view=self)
            return paginator.get_paginated_response(OrderListSerializer(page, many=True).data)
        if _lite(request):
            limit = max(1, min(int_param(request.query_params.get('limit'), 'limit') or 300, 500))
            return Response(OrderListSerializer(self.get_queryset()[:limit], many=True).data)
        limit = max(1, min(int_param(request.query_params.get('limit'), 'limit') or 200, 500))
        return Response(self.get_serializer(self.get_queryset()[:limit], many=True).data)

    def get_object(self):
        order = super().get_object()
        ensure_table_scope(self.request, order.table_id)
        return order

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table_id = serializer.validated_data['table_id']
        ensure_table_scope(request, table_id)
        table = get_object_or_404(Table.objects.select_for_update(), id=table_id)
        if table.status == Table.Status.CLEANING and not is_staff(request):
            raise ValidationError({'detail': 'Bàn đang được dọn, vui lòng chờ nhân viên hoặc gọi nhân viên hỗ trợ.'})

        # Mỗi bàn chỉ có một đơn mở: đặt tiếp sẽ gộp vào đơn hiện tại (gọi thêm món).
        order = Order.objects.select_for_update().filter(table=table, status__in=OPEN_STATUSES).first()
        is_new = order is None
        if is_new:
            order = Order.objects.create(table=table, status=Order.Status.PENDING,
                                         created_by=request.user if is_staff(request) else None)
        _build_items(order, serializer.validated_data['items'])
        recalc_order(order)

        if table.status != Table.Status.OCCUPIED:   # client suy ra trạng thái bàn từ sự kiện new_order
            table.status = Table.Status.OCCUPIED
            table.save(update_fields=['status'])

        order = _order_qs().get(pk=order.pk)
        broadcast_new_order(order)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='add-items')
    @transaction.atomic
    def add_items(self, request, pk=None):
        order = self.get_object()
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status not in OPEN_STATUSES:
            return Response({'detail': 'Đơn đã kết thúc, không thể thêm món.'}, status=status.HTTP_400_BAD_REQUEST)
        if Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).exists():
            return Response({'detail': 'Đơn đã thanh toán, vui lòng tạo đơn mới.'}, status=status.HTTP_400_BAD_REQUEST)
        validator = OrderCreateSerializer(data={'table_id': order.table_id, 'items': request.data.get('items', [])})
        validator.is_valid(raise_exception=True)
        _build_items(order, validator.validated_data['items'])
        recalc_order(order)
        order = _order_qs().get(pk=order.pk)
        broadcast_new_order(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['patch'], url_path='status')
    @transaction.atomic
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status not in Order.Status.values:
            return Response({'detail': 'Trạng thái không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in ORDER_TRANSITIONS.get(order.status, set()):
            return Response({'detail': f'Không thể chuyển đơn từ {order.status} sang {new_status}.'}, status=status.HTTP_400_BAD_REQUEST)
        paid = Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).exists()
        if new_status == 'completed' and not paid:
            return Response({'detail': 'Đơn chưa được thanh toán, không thể hoàn tất.'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status == 'cancelled':
            if paid:
                return Response({'detail': 'Đơn đã thanh toán, hãy hoàn tiền trước khi huỷ.'}, status=status.HTTP_400_BAD_REQUEST)
            if order.items.exclude(status=OrderItem.Status.PENDING).exists() and not has_role(request.user, 'QL', 'AD'):
                return Response({'detail': 'Đơn đã có món đang chế biến, chỉ quản lý mới được huỷ.'}, status=status.HTTP_403_FORBIDDEN)
            Payment.objects.filter(order=order, status=Payment.Status.PENDING).update(status=Payment.Status.FAILED)
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        if new_status in ('cancelled', 'completed'):
            if release_table_if_idle(order.table, Table.Status.EMPTY if new_status == 'cancelled' else Table.Status.CLEANING):
                broadcast_table_updated(order.table)
        broadcast_order_updated(order)
        return Response(OrderSerializer(_order_qs().get(pk=order.pk)).data)


class OrderItemViewSet(viewsets.GenericViewSet):
    """
    PATCH /api/order-items/{id}/status/   → bếp: cooking/done, nhân viên: served (BR-03)
    POST  /api/order-items/{id}/cancel/   → khách / nhân viên huỷ món chưa chế biến
    """
    queryset = OrderItem.objects.select_related('order', 'order__table', 'menu_item', 'menu_item__category')
    serializer_class = OrderItemSerializer

    def get_permissions(self):
        return [AllowAny()] if self.action == 'cancel' else [IsStaffMember()]

    def get_throttles(self):   # RATE-03
        return [CustomerThrottle()] if self.action == 'cancel' else []

    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        order_item = self.get_object()
        serializer = OrderItemStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        current = order_item.status
        if order_item.order.status == Order.Status.CANCELLED:
            return Response({'detail': 'Đơn đã bị huỷ.'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in ITEM_TRANSITIONS.get(current, set()):
            return Response({'detail': f'Không thể chuyển món từ {current} sang {new_status}.'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status == 'served' and not has_role(request.user, 'PV', 'QL', 'AD'):
            return Response({'detail': 'Chỉ nhân viên phục vụ mới xác nhận đã phục vụ.'}, status=status.HTTP_403_FORBIDDEN)
        if new_status in ('cooking', 'done') and not has_role(request.user, 'BEP', 'QL', 'AD'):
            return Response({'detail': 'Chỉ bộ phận bếp mới cập nhật chế biến.'}, status=status.HTTP_403_FORBIDDEN)
        order_item.status = new_status
        order_item.save(update_fields=['status'])

        order = order_item.order
        if new_status == 'cooking' and order.status == Order.Status.PENDING:
            order.status = Order.Status.CONFIRMED   # bếp đã nhận đơn
            order.save(update_fields=['status', 'updated_at'])
        broadcast_item_status(order_item)
        return Response(OrderItemSerializer(order_item).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    @transaction.atomic
    def cancel(self, request, pk=None):
        order_item = self.get_object()
        order = Order.objects.select_for_update().select_related('table').get(pk=order_item.order_id)
        ensure_table_scope(request, order.table_id)
        if order.status not in OPEN_STATUSES:
            return Response({'detail': 'Đơn đã kết thúc.'}, status=status.HTTP_400_BAD_REQUEST)
        order_item.refresh_from_db()
        if order_item.status != OrderItem.Status.PENDING:
            return Response({'detail': 'Món đã được bếp nhận, không thể huỷ.'}, status=status.HTTP_400_BAD_REQUEST)
        order_item.delete()
        if not OrderItem.objects.filter(order=order).exists():
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])
            Payment.objects.filter(order=order, status=Payment.Status.PENDING).update(status=Payment.Status.FAILED)
            if release_table_if_idle(order.table, Table.Status.EMPTY):
                broadcast_table_updated(order.table)
        recalc_order(order)
        broadcast_order_updated(order)
        return Response(OrderSerializer(_order_qs().get(pk=order.pk)).data)
