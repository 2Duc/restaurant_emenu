from django.db import DataError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    """Giá trị vượt phạm vi/kiểu của CSDL (DataError, OverflowError) là lỗi đầu vào của client -> 400, không phải 500."""
    response = drf_exception_handler(exc, context)
    if response is None and isinstance(exc, (DataError, OverflowError)):
        return Response({'detail': 'Tham số không hợp lệ.'}, status=400)
    return response
