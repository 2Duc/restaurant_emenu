from urllib.parse import urlparse
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from ..models import Table, Order, new_qr_token
from ..serializers import TableSerializer, OrderSerializer
from ..permissions import IsManagerOrAdmin, IsWaiterOrManager
from ..services.audit import AuditMixin
from ..services.orders import OPEN_STATUSES
import io
import zipfile
from django.http import HttpResponse
from ..services.qr_service import cards_pdf, png_bytes, table_card_image, table_link, table_qr_data_uri, table_qr_file
from ..services.realtime import broadcast_table_updated
from ..services.scope import ensure_table_scope
from ..services.audit import log_action
from ..services.table_token import MAX_AGE_SECONDS, check_qr_key, make_table_token
from ..params import int_param
from ..throttles import CustomerThrottle, TableSessionThrottle


def _base_url(request):
    """Gốc URL frontend để dựng link QR. Cho phép ?base_url= (vd. http://192.168.1.5:5173 khi test bằng điện thoại)."""
    candidate = (request.query_params.get('base_url') or '').strip().rstrip('/')
    parsed = urlparse(candidate)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return f'{parsed.scheme}://{parsed.netloc}'
    return _default_base()


def _default_base():
    return (getattr(settings, 'PUBLIC_BASE_URL', '') or settings.FRONTEND_BASE_URL).rstrip('/')


def _qr_payload(table, base_url):
    # Mỗi bàn có 1 id; id đó chính là số bàn. Link QR: <base>/table/<id>?k=<qr_token> (k là mã bí mật của bàn).
    # qr_code_url lưu trong DB (và lộ qua API công khai) KHÔNG chứa k.
    public_url = f'{base_url}/table/{table.id}'
    if table.qr_code_url != public_url:
        table.qr_code_url = public_url
        table.save(update_fields=['qr_code_url'])
    # Ảnh QR lưu file bền theo (qr_token, base): chỉ sinh lại khi token hoặc địa chỉ website đổi.
    return {'id': table.id, 'table_id': table.id, 'number': table.number, 'area': table.area,
            'url': table_link(table, base_url), 'qr_image': table_qr_data_uri(table, base_url, size=360),
            'base_url': base_url, 'default_base_url': _default_base()}


def _selected_tables(request, queryset):
    raw = (request.query_params.get('ids') or '').strip()
    if not raw:
        return list(queryset)
    ids = []
    for part in raw.split(','):
        value = int_param(part.strip(), 'ids')
        if value is not None:
            ids.append(value)
    return list(queryset.filter(pk__in=ids))


def _download(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response

class TableViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Table.objects.all().order_by('id')
    serializer_class = TableSerializer
    audit_name = 'TABLE'
    audit_label = 'bàn'
    def get_permissions(self):
        if self.action in ('retrieve', 'by_number', 'current_order', 'session'):
            return [AllowAny()]
        if self.action in ('update_status', 'list', 'qr', 'qr_codes', 'qr_png', 'qr_pdf', 'qr_zip'): return [IsWaiterOrManager()]
        return [IsManagerOrAdmin()]   # gồm rotate_qr (Đổi mã QR) chỉ quản lý / admin

    def get_throttles(self):   # RATE-03
        if self.action == 'session':
            return [TableSessionThrottle()]
        return [CustomerThrottle()] if self.action in ('current_order',) else []

    @action(detail=False, methods=['post'], url_path='session', authentication_classes=[])
    def session(self, request):
        """POST /api/tables/session/ {table_id, k} → token phiên bàn ký (hạn 6 giờ) dùng cho header X-Table-Token / ws ?token=."""
        table_id = int_param(request.data.get('table_id'), 'table_id')
        key = request.data.get('k')
        table = Table.objects.filter(pk=table_id).first() if table_id is not None else None
        if table is None or not isinstance(key, str) or not check_qr_key(table, key):
            return Response({'detail': 'Mã QR không hợp lệ hoặc đã hết hiệu lực. Vui lòng quét lại mã QR trên bàn.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'token': make_table_token(table), 'table_id': table.id, 'expires_in': MAX_AGE_SECONDS})

    @action(detail=True, methods=['post'], url_path='rotate-qr')
    def rotate_qr(self, request, pk=None):
        """POST /api/tables/<id>/rotate-qr/ — Đổi mã QR: sinh qr_token mới, QR cũ và mọi phiên bàn đang mở mất hiệu lực."""
        table = self.get_object()
        table.qr_token = new_qr_token()
        table.save(update_fields=['qr_token'])
        log_action(request, 'TABLE_QR_ROTATE', f'Đổi mã QR bàn {table.number}', {'id': table.pk})
        return Response(_qr_payload(table, _base_url(request)))
    @action(detail=False, methods=['get'], url_path=r'by-number/(?P<number>[^/.]+)', permission_classes=[AllowAny])
    def by_number(self, request, number=None):
        return Response(self.get_serializer(get_object_or_404(Table, number=number)).data)
    @action(detail=True, methods=['get'], url_path='current-order', permission_classes=[AllowAny])
    def current_order(self, request, pk=None):
        table = self.get_object()
        ensure_table_scope(request, table.id)
        order = Order.objects.filter(table=table, status__in=OPEN_STATUSES).order_by('-created_at').first()
        if not order: return Response({'detail': 'Không có đơn đang mở'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderSerializer(order).data)
    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        table = self.get_object()
        new_status = request.data.get('status')
        if new_status not in Table.Status.values:
            return Response({'detail': 'Trạng thái không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status == Table.Status.EMPTY and Order.objects.filter(table=table, status__in=OPEN_STATUSES).exists():
            return Response({'detail': 'Bàn còn đơn chưa thanh toán, không thể chuyển về trống.'}, status=status.HTTP_400_BAD_REQUEST)
        table.status = new_status
        table.save(update_fields=['status'])
        broadcast_table_updated(table)
        return Response(self.get_serializer(table).data)

    def destroy(self, request, *args, **kwargs):
        table = self.get_object()
        if table.orders.exists():
            return Response({'detail': 'Bàn đã có lịch sử đơn hàng, không thể xoá.'}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_destroy(table)
        return Response(status=status.HTTP_204_NO_CONTENT)
    @action(detail=True, methods=['get'], url_path='qr')
    def qr(self, request, pk=None):
        """GET /api/tables/<id>/qr/ → link vào bàn + ảnh QR (data URI)."""
        return Response(_qr_payload(self.get_object(), _base_url(request)))
    @action(detail=False, methods=['get'], url_path='qr-codes')
    def qr_codes(self, request):
        """GET /api/tables/qr-codes/ → QR của toàn bộ bàn (để in)."""
        base = _base_url(request)
        return Response([_qr_payload(t, base) for t in self.get_queryset()])

    @action(detail=True, methods=['get'], url_path='qr-png')
    def qr_png(self, request, pk=None):
        """GET /api/tables/<id>/qr-png/?card=1 -> PNG của QR bàn (card=1: thẻ dán bàn đủ tên quán, số bàn, hướng dẫn)."""
        table, base = self.get_object(), _base_url(request)
        if request.query_params.get('card') in ('1', 'true'):
            return _download(png_bytes(table_card_image(table, base)), 'image/png', f'the-ban-{table.id}.png')
        return _download(table_qr_file(table, base).read_bytes(), 'image/png', f'qr-ban-{table.id}.png')

    @action(detail=False, methods=['get'], url_path='qr-pdf')
    def qr_pdf(self, request):
        """GET /api/tables/qr-pdf/?ids=1,2 -> PDF A4, 4 thẻ mỗi trang (bỏ ids = tất cả bàn)."""
        tables = _selected_tables(request, self.get_queryset())
        if not tables:
            return Response({'detail': 'Không có bàn nào để in.'}, status=status.HTTP_404_NOT_FOUND)
        return _download(cards_pdf(tables, _base_url(request)), 'application/pdf', 'the-ban-abc-restaurant.pdf')

    @action(detail=False, methods=['get'], url_path='qr-zip')
    def qr_zip(self, request):
        """GET /api/tables/qr-zip/?ids=1,2 -> zip các thẻ PNG (bỏ ids = tất cả bàn)."""
        tables = _selected_tables(request, self.get_queryset())
        if not tables:
            return Response({'detail': 'Không có bàn nào để tải.'}, status=status.HTTP_404_NOT_FOUND)
        base, buffer = _base_url(request), io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
            for table in tables:
                archive.writestr(f'the-ban-{table.id}.png', png_bytes(table_card_image(table, base)))
        return _download(buffer.getvalue(), 'application/zip', 'the-ban-abc-restaurant.zip')
