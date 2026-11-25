from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Order, Payment, Promotion
from ..permissions import IsManagerOrAdmin
from ..serializers import OrderSerializer, PromotionSerializer
from ..services.audit import AuditMixin
from ..services.orders import OPEN_STATUSES, promotion_base, recalc_order
from ..services.realtime import broadcast_order_updated
from ..services.scope import ensure_table_scope
from ..throttles import CustomerThrottle


def _active_promotions():
    now = timezone.now()
    return Promotion.objects.filter(is_active=True, start_date__lte=now, end_date__gte=now)


class PromotionViewSet(AuditMixin, viewsets.ModelViewSet):
    """BR-05: quản lý mã khuyến mãi (giảm % hoặc số tiền cố định, cho cả đơn hoặc riêng một món).

    Quản lý thấy toàn bộ mã; khách chỉ thấy mã đang hiệu lực.
    """
    serializer_class = PromotionSerializer
    audit_name = 'PROMOTION'
    audit_label = 'khuyến mãi'

    def get_permissions(self):
        return [AllowAny()] if self.request.method in ('GET', 'HEAD', 'OPTIONS') else [IsManagerOrAdmin()]

    def get_queryset(self):
        if IsManagerOrAdmin().has_permission(self.request, self) and self.action != 'active':
            return Promotion.objects.select_related('menu_item').order_by('-start_date')
        return _active_promotions().select_related('menu_item').order_by('-start_date')

    def destroy(self, request, *args, **kwargs):
        promo = self.get_object()
        if promo.orders.exists():
            promo.is_active = False   # đã dùng cho đơn → chỉ tắt để giữ lịch sử hoá đơn
            promo.save(update_fields=['is_active'])
            return Response({'detail': 'Mã đã được dùng nên chỉ được tắt, không xoá.'}, status=status.HTTP_200_OK)
        self.perform_destroy(promo)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)


class ApplyPromotionAPIView(APIView):
    """POST /api/orders/{id}/apply-promotion/ {code} — code rỗng để gỡ mã."""
    permission_classes = [AllowAny]
    throttle_classes = [CustomerThrottle]   # RATE-03

    @transaction.atomic
    def post(self, request, pk):
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
        ensure_table_scope(request, order.table_id)
        if order.status not in OPEN_STATUSES:
            return Response({'detail': 'Đơn đã kết thúc, không thể áp dụng mã.'}, status=status.HTTP_400_BAD_REQUEST)
        if Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).exists():
            return Response({'detail': 'Đơn đã thanh toán.'}, status=status.HTTP_400_BAD_REQUEST)
        code = str(request.data.get('code', '')).strip().upper()
        if not code:
            order.promotion = None
        else:
            promotion = _active_promotions().select_related('menu_item').filter(code=code).first()
            if promotion is None:
                return Response({'detail': 'Mã khuyến mãi không tồn tại hoặc đã hết hạn.'}, status=status.HTTP_400_BAD_REQUEST)
            if promotion.menu_item_id and promotion_base(order, promotion) <= 0:
                return Response({'detail': f'Mã {promotion.code} chỉ áp dụng cho món {promotion.menu_item.name}.'},
                                status=status.HTTP_400_BAD_REQUEST)
            order.promotion = promotion
        order.save(update_fields=['promotion', 'updated_at'])
        recalc_order(order)
        broadcast_order_updated(order)
        return Response(OrderSerializer(Order.objects.prefetch_related('items__menu_item__category').get(pk=order.pk)).data)
