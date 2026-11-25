from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AuditLog, UserAccount
from ..params import int_param
from ..permissions import IsManagerOrAdmin
from ..serializers import AuditLogSerializer, StaffSerializer
from ..services.audit import AuditMixin, log_action


class UserViewSet(AuditMixin, viewsets.ModelViewSet):
    """Quản lý tài khoản nhân viên (quản lý/admin). Không xoá — chỉ khoá (is_active=false) để giữ lịch sử đơn."""
    queryset = UserAccount.objects.all().order_by('role', 'username')
    serializer_class = StaffSerializer
    permission_classes = [IsManagerOrAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    audit_name = 'STAFF'
    audit_label = 'tài khoản'

    def _audit_text(self, obj):
        return f'{obj.username} ({obj.role})'

    def perform_update(self, serializer):
        target = serializer.instance
        data = serializer.validated_data
        if target.pk == self.request.user.pk and (data.get('is_active') is False or ('role' in data and data['role'] != target.role)):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Không thể tự khoá hoặc đổi vai trò của chính mình.'})
        return super().perform_update(serializer)


class AuditLogAPIView(APIView):
    """GET /api/audit-logs/ — danh sách nhật ký; POST — ghi việc chuyển chế độ Phục vụ / Quản lý."""
    def get_permissions(self):
        return [IsManagerOrAdmin()]

    def get(self, request):
        limit = max(1, min(int_param(request.query_params.get('limit'), 'limit') or 100, 500))
        return Response(AuditLogSerializer(AuditLog.objects.all()[:limit], many=True).data)

    def post(self, request):
        action = request.data.get('action')
        if action != 'SWITCH_MODE':
            return Response({'detail': 'Hành động không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)
        mode = request.data.get('mode') if request.data.get('mode') in ('waiter', 'manager') else 'manager'
        entry = log_action(request, 'SWITCH_MODE', f'Chuyển sang chế độ {"Phục vụ" if mode == "waiter" else "Quản lý"}', {'reason': str(request.data.get('reason', ''))[:200]}, mode=mode)
        return Response(AuditLogSerializer(entry).data, status=status.HTTP_201_CREATED)
