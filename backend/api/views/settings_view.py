from django.db import transaction
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import SystemSetting
from ..permissions import IsAdmin, has_role
from ..serializers import SystemSettingSerializer
from ..services.audit import log_action
from ..services.system_settings import gateway_status, public_payload
from ..throttles import CustomerThrottle


class SystemSettingAPIView(APIView):
    """GET /api/settings/ — công khai: phương thức thanh toán bật + TK nhận; Admin nhận thêm toàn bộ cấu hình + trạng thái cổng.
    PATCH /api/settings/ — chỉ Admin, có audit."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == 'PATCH' else [AllowAny()]

    def get_throttles(self):
        return [CustomerThrottle()] if self.request.method == 'GET' and not has_role(self.request.user, 'AD') else []

    def _full(self, cfg):
        data = public_payload(cfg)
        data['config'] = SystemSettingSerializer(cfg).data
        data['gateway'] = gateway_status()
        return data

    def get(self, request):
        cfg = SystemSetting.load()
        return Response(self._full(cfg) if has_role(request.user, 'AD') else public_payload(cfg))

    @transaction.atomic
    def patch(self, request):
        cfg = SystemSetting.objects.select_for_update().get_or_create(pk=1)[0]
        serializer = SystemSettingSerializer(cfg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(updated_by=request.user)
        log_action(request, 'SYSTEM_SETTING_UPDATE', 'Cập nhật cấu hình hệ thống', {'fields': sorted(serializer.validated_data.keys())}, mode='admin')
        return Response(self._full(obj))
