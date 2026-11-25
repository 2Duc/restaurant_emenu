from django.contrib.auth import authenticate, get_user_model, update_session_auth_hash
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from ..serializers import ChangePasswordSerializer, LoginSerializer, ReauthSerializer, UserSerializer
from ..services.audit import log_action

User = get_user_model()


class LoginAPIView(APIView):
    """BR-07: Nhân viên / Bếp / Quản lý / Admin đăng nhập JWT theo vai trò."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username'].strip()
        if '@' in username:
            account = User.objects.filter(email__iexact=username).only('username').first()
            username = account.username if account else username
        user = authenticate(username=username, password=serializer.validated_data['password'])
        if user is None or not user.is_active:
            return Response({'detail': 'Sai tên đăng nhập hoặc mật khẩu.'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'user': UserSerializer(user).data})


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ReauthAPIView(APIView):
    """POST /api/auth/reauth/ {password} — xác nhận lại mật khẩu trước thao tác nhạy cảm (quay lại chế độ quản lý)."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'reauth'

    def post(self, request):
        serializer = ReauthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['password']):
            log_action(request, 'REAUTH_FAILED', 'Nhập lại mật khẩu không đúng')
            return Response({'detail': 'Mật khẩu không đúng.'}, status=status.HTTP_403_FORBIDDEN)
        log_action(request, 'REAUTH_OK', 'Xác nhận lại mật khẩu')
        return Response({'detail': 'OK'})


class ChangePasswordAPIView(APIView):
    """POST /api/auth/change-password/ {old_password, new_password}"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'reauth'

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'old_password': ['Mật khẩu hiện tại không đúng.']}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        update_session_auth_hash(request, user)
        log_action(request, 'PASSWORD_CHANGE', 'Đổi mật khẩu')
        return Response({'detail': 'Đã đổi mật khẩu.'})
