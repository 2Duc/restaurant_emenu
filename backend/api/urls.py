# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views.table_view import TableViewSet
from .views.menu_view import CategoryViewSet, MenuItemViewSet
from .views.order_view import OrderViewSet, OrderItemViewSet
from .views.payment_view import (
    PaymentCreateAPIView, PaymentCashConfirmAPIView, PaymentManualConfirmAPIView, PaymentListAPIView, PaymentDetailAPIView, PaymentSyncAPIView,
    PaymentQueryAPIView, PaymentRefundAPIView, VNPayReturnAPIView, VNPayIPNAPIView, MockGatewayCallbackAPIView,
)
from .views.auth_view import LoginAPIView, MeAPIView, ReauthAPIView, ChangePasswordAPIView
from .views.promotion_view import PromotionViewSet, ApplyPromotionAPIView
from .views.review_view import ReviewViewSet
from .views.staff_call_view import StaffCallViewSet
from .views.report_view import ReportSummaryAPIView
from .views.settings_view import SystemSettingAPIView
from .views.user_view import UserViewSet, AuditLogAPIView

router = DefaultRouter()
router.register(r'tables', TableViewSet, basename='table')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'menu-items', MenuItemViewSet, basename='menuitem')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'order-items', OrderItemViewSet, basename='orderitem')
router.register(r'promotions', PromotionViewSet, basename='promotion')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'staff-calls', StaffCallViewSet, basename='staff-call')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)),
    # Auth
    path('auth/login/', LoginAPIView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', MeAPIView.as_view(), name='me'),
    path('auth/reauth/', ReauthAPIView.as_view(), name='reauth'),
    path('auth/change-password/', ChangePasswordAPIView.as_view(), name='change-password'),

    # Payment
    path('payments/', PaymentListAPIView.as_view(), name='payment-list'),
    path('payments/create/', PaymentCreateAPIView.as_view(), name='payment-create'),
    path('payments/vnpay-return/', VNPayReturnAPIView.as_view(), name='vnpay-return'),
    path('payments/vnpay-ipn/', VNPayIPNAPIView.as_view(), name='vnpay-ipn'),
    path('payments/mock-callback/', MockGatewayCallbackAPIView.as_view(), name='payment-mock-callback'),
    path('payments/query/', PaymentQueryAPIView.as_view(), name='payment-query'),
    path('payments/refund/', PaymentRefundAPIView.as_view(), name='payment-refund'),
    path('payments/<int:pk>/', PaymentDetailAPIView.as_view(), name='payment-detail'),
    path('payments/<int:pk>/sync/', PaymentSyncAPIView.as_view(), name='payment-sync'),
    path('payments/<int:pk>/confirm-manual/', PaymentManualConfirmAPIView.as_view(), name='payment-confirm-manual'),
    path('payments/<int:pk>/confirm-cash/', PaymentCashConfirmAPIView.as_view(), name='payment-confirm-cash'),

    path('settings/', SystemSettingAPIView.as_view(), name='system-settings'),
    path('audit-logs/', AuditLogAPIView.as_view(), name='audit-logs'),
    path('reports/summary/', ReportSummaryAPIView.as_view(), name='report-summary'),

    # Promotion apply
    path('orders/<int:pk>/apply-promotion/', ApplyPromotionAPIView.as_view(), name='apply-promotion'),
]