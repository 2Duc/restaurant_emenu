from ..models import AuditLog


def log_action(request, action, title, payload=None, mode='manager'):
    user = getattr(request, 'user', None)
    authed = bool(user and user.is_authenticated)
    return AuditLog.objects.create(
        actor=user if authed else None,
        actor_name=user.username if authed else 'anonymous',
        acted_mode=mode, action=action, title=title[:255], payload=payload or {},
    )


class AuditMixin:
    """Gắn vào ModelViewSet: tự ghi nhật ký khi tạo / sửa / xoá."""
    audit_name = 'OBJECT'      # tiền tố mã hành động, vd MENU_ITEM -> MENU_ITEM_CREATE
    audit_label = 'đối tượng'  # dùng trong tiêu đề tiếng Việt

    def _audit_text(self, obj):
        return str(obj)

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(self.request, f'{self.audit_name}_CREATE', f'Tạo {self.audit_label}: {self._audit_text(obj)}', {'id': obj.pk})
        return obj

    def perform_update(self, serializer):
        obj = serializer.save()
        changed = [k for k in serializer.validated_data.keys() if k != 'password']
        log_action(self.request, f'{self.audit_name}_UPDATE', f'Cập nhật {self.audit_label}: {self._audit_text(obj)}', {'id': obj.pk, 'fields': changed})
        return obj

    def perform_destroy(self, instance):
        label, pk = self._audit_text(instance), instance.pk
        instance.delete()
        log_action(self.request, f'{self.audit_name}_DELETE', f'Xoá {self.audit_label}: {label}', {'id': pk})
