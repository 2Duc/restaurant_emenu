from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import Category, MenuItem
from ..permissions import IsKitchenOrManager, IsManagerOrAdmin, IsStaffMember
from ..serializers import CategorySerializer, MenuItemSerializer
from ..services.audit import AuditMixin, log_action
from ..services.realtime import broadcast_menu_updated

READ_METHODS = ('GET', 'HEAD', 'OPTIONS')
MENU_VER_KEY = 'menu_cache_ver'


def bump_menu_cache():
    try:
        cache.incr(MENU_VER_KEY)
    except ValueError:
        cache.set(MENU_VER_KEY, 1, None)


class PublicListCacheMixin:
    """Cache ngắn danh sách GET cho khách (không đăng nhập nhân viên); invalidate qua bump_menu_cache()."""
    cache_prefix = ''

    def list(self, request, *args, **kwargs):
        ttl = getattr(settings, 'MENU_CACHE_TTL', 0)
        if ttl <= 0 or IsStaffMember().has_permission(request, self):
            return super().list(request, *args, **kwargs)
        key = f'{self.cache_prefix}:{cache.get(MENU_VER_KEY, 0)}:{request.get_host()}:{request.get_full_path()}'
        data = cache.get(key)
        if data is None:
            data = super().list(request, *args, **kwargs).data
            cache.set(key, data, ttl)
        return Response(data)


class CategoryViewSet(PublicListCacheMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('sort_order', 'name')
    serializer_class = CategorySerializer
    cache_prefix = 'cat'
    audit_name = 'CATEGORY'
    audit_label = 'danh mục'

    def get_permissions(self):
        return [AllowAny()] if self.request.method in READ_METHODS else [IsManagerOrAdmin()]

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.menu_items.exists():
            return Response({'detail': 'Danh mục còn món ăn, hãy chuyển hoặc xoá món trước.'}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_destroy(category)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemViewSet(PublicListCacheMixin, AuditMixin, viewsets.ModelViewSet):
    """BR-08: món ăn hỗ trợ upload ảnh (multipart, trường image_url)."""
    serializer_class = MenuItemSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_available']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['price', 'name']
    cache_prefix = 'menu'
    audit_name = 'MENU_ITEM'
    audit_label = 'món'

    def get_queryset(self):
        qs = MenuItem.objects.select_related('category').annotate(
            avg_rating_value=Avg('order_items__review__rating'),
            review_count_value=Count('order_items__review'),
        ).order_by('category__sort_order', 'name')
        if self.request.method in READ_METHODS and not IsStaffMember().has_permission(self.request, self):
            qs = qs.filter(is_available=True)   # khách chỉ thấy món đang bán
        return qs

    def get_permissions(self):
        if self.request.method in READ_METHODS:
            return [AllowAny()]
        if self.action == 'availability':
            return [IsKitchenOrManager()]
        return [IsManagerOrAdmin()]

    def perform_update(self, serializer):
        obj = super().perform_update(serializer)
        broadcast_menu_updated(obj)
        return obj

    def destroy(self, request, *args, **kwargs):
        item = self.get_object()
        if item.order_items.exists():
            return Response({'detail': 'Món đã có trong đơn hàng, không thể xoá. Hãy chuyển sang "Ngừng bán".'},
                            status=status.HTTP_409_CONFLICT)
        if item.image_url:
            item.image_url.delete(save=False)
        self.perform_destroy(item)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='availability')
    def availability(self, request, pk=None):
        """POST /api/menu-items/<id>/availability/ {is_available} — bếp báo hết / còn món."""
        item = self.get_object()
        value = request.data.get('is_available')
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ('1', 'true', 'yes', 'on'):
                value = True
            elif text in ('0', 'false', 'no', 'off'):
                value = False
        if not isinstance(value, bool):
            return Response({'detail': 'is_available phải là true/false.'}, status=status.HTTP_400_BAD_REQUEST)
        item.is_available = value
        item.save(update_fields=['is_available'])
        log_action(request, 'MENU_ITEM_AVAILABILITY', f'{"Mở bán" if value else "Ngừng bán"} món: {item.name}',
                   {'id': item.pk, 'is_available': value})
        broadcast_menu_updated(item)
        return Response(self.get_serializer(item).data)
