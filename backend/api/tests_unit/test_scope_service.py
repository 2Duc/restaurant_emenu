"""Unit test cho api/services/scope.py (BR-02)."""
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import PermissionDenied

from ..models import Table
from ..services.scope import customer_table_id, ensure_table_scope, is_staff
from ..services.table_token import make_table_token


def req(token=None, user=None, table_id_header=None):
    meta = {}
    if token is not None:
        meta['HTTP_X_TABLE_TOKEN'] = token
    if table_id_header is not None:
        meta['HTTP_X_TABLE_ID'] = table_id_header
    return SimpleNamespace(META=meta, user=user)


def user(role='PV', superuser=False, authed=True):
    return SimpleNamespace(is_authenticated=authed, is_superuser=superuser, role=role)


class CustomerTableIdTests(TestCase):
    def setUp(self):
        self.t5 = Table.objects.create(area='A')

    def test_returns_id_from_valid_token(self):
        """Token hợp lệ -> id bàn dạng chuỗi."""
        self.assertEqual(customer_table_id(req(make_table_token(self.t5))), str(self.t5.id))

    def test_strips_whitespace(self):
        """Token có khoảng trắng hai đầu vẫn hợp lệ."""
        self.assertEqual(customer_table_id(req(f' {make_table_token(self.t5)} ')), str(self.t5.id))

    def test_missing_header_is_none(self):
        """Không có header -> None."""
        self.assertIsNone(customer_table_id(req()))

    def test_x_table_id_is_ignored(self):
        """X-Table-Id tự khai không còn được tin (AUTH-05)."""
        self.assertIsNone(customer_table_id(req(table_id_header=str(self.t5.id))))

    def test_garbage_and_tampered_tokens_are_none(self):
        """Token rác / bị sửa chữ ký -> None."""
        good = make_table_token(self.t5)
        for bad in ('abc', '', '1', '1:abc:def', good[:-2] + 'xx', good + 'x'):
            self.assertIsNone(customer_table_id(req(bad)), bad)


class IsStaffTests(SimpleTestCase):
    def test_staff_roles_are_staff(self):
        """PV, BEP, QL, AD đều là nhân viên."""
        for role in ('PV', 'BEP', 'QL', 'AD'):
            self.assertTrue(is_staff(req(user=user(role))), role)

    def test_superuser_is_staff_regardless_of_role(self):
        """Superuser luôn là nhân viên."""
        self.assertTrue(is_staff(req(user=user('XX', superuser=True))))

    def test_anonymous_or_unknown_role_is_not_staff(self):
        """Chưa đăng nhập, không có user hoặc role lạ -> không phải nhân viên."""
        self.assertFalse(is_staff(req(user=user(authed=False))))
        self.assertFalse(is_staff(req(user=None)))
        self.assertFalse(is_staff(req(user=user('KH'))))
        self.assertFalse(is_staff(SimpleNamespace(META={})))


class EnsureTableScopeTests(TestCase):
    def setUp(self):
        self.t3 = Table.objects.create(area='A')
        self.t4 = Table.objects.create(area='B')

    def test_customer_matching_table_passes(self):
        """Khách đúng bàn (id int hoặc str) -> được phép."""
        ensure_table_scope(req(make_table_token(self.t3)), self.t3.id)
        ensure_table_scope(req(make_table_token(self.t3)), str(self.t3.id))

    def test_customer_other_table_denied(self):
        """Khách thao tác bàn khác -> PermissionDenied."""
        with self.assertRaises(PermissionDenied):
            ensure_table_scope(req(make_table_token(self.t3)), self.t4.id)

    def test_customer_without_token_denied(self):
        """Khách không gửi X-Table-Token (kể cả có X-Table-Id) -> bị từ chối."""
        with self.assertRaises(PermissionDenied):
            ensure_table_scope(req(), self.t3.id)
        with self.assertRaises(PermissionDenied):
            ensure_table_scope(req(table_id_header=str(self.t3.id)), self.t3.id)

    def test_customer_with_none_table_denied(self):
        """table_id None -> bị từ chối."""
        with self.assertRaises(PermissionDenied):
            ensure_table_scope(req(make_table_token(self.t3)), None)

    def test_staff_bypasses_scope(self):
        """Nhân viên không bị giới hạn bàn, kể cả khi không có header."""
        ensure_table_scope(req(user=user('PV')), 99)
