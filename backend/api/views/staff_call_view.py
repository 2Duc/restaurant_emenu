from datetime import timedelta

from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import StaffCall, SystemSetting
from ..permissions import IsWaiterOrManager
from ..serializers import StaffCallSerializer
from ..services.realtime import broadcast_staff_call
from ..params import int_param
from ..services.scope import ensure_table_scope
from ..throttles import CustomerThrottle, StaffCallThrottle

TRANSITIONS = {'pending': {'accepted', 'resolved'}, 'accepted': {'resolved'}, 'resolved': set()}


class StaffCallViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Khách gọi nhân viên (không đăng nhập, chỉ cho bàn mình); nhân viên tiếp nhận / hoàn thành."""
    queryset = StaffCall.objects.select_related('table', 'handled_by').all()
    serializer_class = StaffCallSerializer

    def get_permissions(self):
        return [AllowAny()] if self.action == 'create' else [IsWaiterOrManager()]

    def get_throttles(self):   # RATE-03
        return [StaffCallThrottle(), CustomerThrottle()] if self.action == 'create' else []

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        return qs.filter(status=status_filter) if status_filter else qs

    def create(self, request, *args, **kwargs):
        ensure_table_scope(request, int_param(request.data.get('table'), 'table'))
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table = serializer.validated_data['table']
        # Chống spam: đã có yêu cầu đang chờ trong N phút gần đây (cấu hình hệ thống, mặc định 2) thì dùng lại.
        recent = StaffCall.objects.filter(table=table, status=StaffCall.Status.PENDING,
                                          created_at__gte=timezone.now() - timedelta(minutes=SystemSetting.load().staff_call_cooldown_minutes)).first()
        if recent:
            return Response(self.get_serializer(recent).data, status=status.HTTP_200_OK)
        call = serializer.save()
        broadcast_staff_call(call)
        return Response(self.get_serializer(call).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        call = self.get_object()
        new_status = request.data.get('status')
        if new_status not in TRANSITIONS.get(call.status, set()):
            return Response({'detail': 'Trạng thái không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)
        call.status = new_status
        call.handled_by = request.user
        call.save(update_fields=['status', 'handled_by'])
        broadcast_staff_call(call)
        return Response(self.get_serializer(call).data)
