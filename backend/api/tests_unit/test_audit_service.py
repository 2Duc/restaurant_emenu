"""Unit test cho api/services/audit.py."""
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from ..models import AuditLog, Category, UserAccount
from ..services.audit import AuditMixin, log_action


class LogActionTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user('ql1', password='x', role='QL')

    def test_logs_authenticated_actor(self):
        """User đăng nhập -> ghi actor và actor_name."""
        log = log_action(SimpleNamespace(user=self.user), 'X_CREATE', 'Tạo X', {'id': 1})
        self.assertEqual((log.actor, log.actor_name, log.action, log.payload, log.acted_mode),
                         (self.user, 'ql1', 'X_CREATE', {'id': 1}, 'manager'))

    def test_anonymous_is_logged_as_anonymous(self):
        """Chưa đăng nhập -> actor None, tên 'anonymous'."""
        log = log_action(SimpleNamespace(user=AnonymousUser()), 'A', 'T')
        self.assertIsNone(log.actor)
        self.assertEqual(log.actor_name, 'anonymous')

    def test_request_without_user_attribute(self):
        """Request không có thuộc tính user vẫn ghi được."""
        self.assertEqual(log_action(SimpleNamespace(), 'A', 'T').actor_name, 'anonymous')

    def test_title_truncated_to_255_and_payload_default(self):
        """Tiêu đề dài bị cắt 255; payload mặc định {}."""
        log = log_action(SimpleNamespace(user=self.user), 'A', 'x' * 400)
        self.assertEqual(len(log.title), 255)
        self.assertEqual(log.payload, {})

    def test_custom_mode(self):
        """Tham số mode được lưu vào acted_mode."""
        self.assertEqual(log_action(SimpleNamespace(user=self.user), 'A', 'T', mode='waiter').acted_mode, 'waiter')


class FakeSerializer:
    def __init__(self, obj=None, data=None):
        self.obj, self.validated_data = obj, data or {}

    def save(self):
        return self.obj


class AuditMixinTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user('ql1', password='x', role='QL')
        self.cat = Category.objects.create(name='Món')

        class View(AuditMixin):
            audit_name, audit_label = 'CATEGORY', 'danh mục'
        self.view = View()
        self.view.request = SimpleNamespace(user=self.user)

    def test_create_logs_action(self):
        """perform_create ghi CATEGORY_CREATE."""
        self.view.perform_create(FakeSerializer(self.cat))
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.title, log.payload), ('CATEGORY_CREATE', 'Tạo danh mục: Món', {'id': self.cat.pk}))

    def test_update_logs_changed_fields_without_password(self):
        """perform_update liệt kê trường đã đổi, loại 'password'."""
        self.view.perform_update(FakeSerializer(self.cat, {'name': 'n', 'password': 'p'}))
        self.assertEqual(AuditLog.objects.get().payload['fields'], ['name'])

    def test_destroy_deletes_and_logs_with_old_label(self):
        """perform_destroy xoá đối tượng và ghi tên cũ + id cũ."""
        pk = self.cat.pk
        self.view.perform_destroy(self.cat)
        self.assertFalse(Category.objects.filter(pk=pk).exists())
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.title, log.payload), ('CATEGORY_DELETE', 'Xoá danh mục: Món', {'id': pk}))
