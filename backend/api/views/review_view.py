from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from ..models import OrderItem, Review
from ..params import int_param
from ..serializers import ReviewSerializer
from ..services.scope import customer_table_id, ensure_table_scope, is_staff
from ..throttles import CustomerThrottle, ReviewThrottle


class ReviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    POST /api/reviews/ {order_item, rating, comment}  — khách đánh giá món đã phục vụ (BR-02: chỉ món của bàn mình)
    GET  /api/reviews/?order_id=&menu_item=&rating=   — nhân viên xem tất cả; khách chỉ thấy đánh giá của bàn mình
    """
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_throttles(self):   # RATE-03
        return [ReviewThrottle(), CustomerThrottle()] if self.action == 'create' else [CustomerThrottle()]

    def get_queryset(self):
        qs = Review.objects.select_related('order_item__menu_item', 'order_item__order').order_by('-created_at')
        if not is_staff(self.request):
            table_id = customer_table_id(self.request)
            qs = qs.filter(order_item__order__table_id=table_id) if table_id else qs.none()
        p = self.request.query_params
        order_id = int_param(p.get('order_id'), 'order_id')
        menu_item = int_param(p.get('menu_item'), 'menu_item')
        rating = int_param(p.get('rating'), 'rating')
        if order_id is not None:
            qs = qs.filter(order_item__order_id=order_id)
        if menu_item is not None:
            qs = qs.filter(order_item__menu_item_id=menu_item)
        if rating is not None:
            qs = qs.filter(rating=rating)
        return qs

    def create(self, request, *args, **kwargs):
        item = OrderItem.objects.select_related('order').filter(pk=int_param(request.data.get('order_item'), 'order_item')).first()
        if item:
            ensure_table_scope(request, item.order.table_id)
        return super().create(request, *args, **kwargs)
