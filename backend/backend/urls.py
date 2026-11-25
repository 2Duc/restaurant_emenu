from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve


def health(request):
    """GET /api/health/ — dùng cho health check của Railway; kiểm tra luôn kết nối CSDL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'error', 'database': 'down'}, status=503)
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/', include('api.urls')),
    # Ảnh món ăn do quản lý tải lên. Đủ dùng cho quy mô nhà hàng nhỏ; MEDIA_ROOT cần nằm trên Volume bền vững.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
