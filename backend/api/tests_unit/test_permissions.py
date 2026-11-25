"""Unit test cho api/permissions.py."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from .. import permissions as p

ROLES = ('AD', 'QL', 'PV', 'BEP')


def request(role=None, superuser=False, authed=True):
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=authed, is_superuser=superuser, role=role))


class PermissionMatrixTests(SimpleTestCase):
    MATRIX = {
        p.IsStaffMember: {'AD', 'QL', 'PV', 'BEP'},
        p.IsWaiterOrManager: {'AD', 'QL', 'PV'},
        p.IsKitchenOrManager: {'AD', 'QL', 'BEP'},
        p.IsManagerOrAdmin: {'AD', 'QL'},
        p.IsAdmin: {'AD'},
    }

    def test_each_role_against_each_permission(self):
        """Ma trận vai trò x quyền: đúng vai trò mới được qua."""
        for perm, allowed in self.MATRIX.items():
            for role in ROLES:
                self.assertEqual(perm().has_permission(request(role), None), role in allowed, (perm.__name__, role))

    def test_superuser_passes_everything(self):
        """Superuser qua mọi quyền kể cả role lạ."""
        for perm in self.MATRIX:
            self.assertTrue(perm().has_permission(request('KH', superuser=True), None))

    def test_anonymous_denied(self):
        """Chưa đăng nhập hoặc user None -> bị chặn."""
        for perm in self.MATRIX:
            self.assertFalse(perm().has_permission(request('AD', authed=False), None))
            self.assertFalse(perm().has_permission(SimpleNamespace(user=None), None))

    def test_unknown_role_denied(self):
        """Role lạ không phải superuser -> bị chặn."""
        for perm in self.MATRIX:
            self.assertFalse(perm().has_permission(request('XX'), None))

    def test_base_has_role_denies_by_default(self):
        """HasRole không khai báo allowed_roles -> chặn mọi người (trừ superuser)."""
        self.assertFalse(p.HasRole().has_permission(request('AD'), None))
        self.assertTrue(p.HasRole().has_permission(request('AD', superuser=True), None))


class HasRoleFunctionTests(SimpleTestCase):
    def test_role_in_list(self):
        """has_role đúng khi role nằm trong danh sách."""
        self.assertTrue(p.has_role(request('QL').user, 'QL', 'AD'))
        self.assertFalse(p.has_role(request('PV').user, 'QL', 'AD'))

    def test_superuser_and_anonymous(self):
        """Superuser luôn True; anonymous/None luôn False."""
        self.assertTrue(p.has_role(request('PV', superuser=True).user, 'AD'))
        self.assertFalse(p.has_role(request('AD', authed=False).user, 'AD'))
        self.assertFalse(p.has_role(None, 'AD'))

    def test_no_roles_given(self):
        """Không truyền role nào -> False với user thường."""
        self.assertFalse(p.has_role(request('AD').user))
