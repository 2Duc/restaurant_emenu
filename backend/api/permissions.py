from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in self.allowed_roles
        ))


class IsStaffMember(HasRole):
    allowed_roles = ('PV', 'BEP', 'QL', 'AD')


class IsWaiterOrManager(HasRole):
    allowed_roles = ('PV', 'QL', 'AD')


class IsKitchenOrManager(HasRole):
    allowed_roles = ('BEP', 'QL', 'AD')


class IsManagerOrAdmin(HasRole):
    allowed_roles = ('QL', 'AD')


class IsAdmin(HasRole):
    allowed_roles = ('AD',)


def has_role(user, *roles):
    return bool(user and user.is_authenticated and (user.is_superuser or user.role in roles))
