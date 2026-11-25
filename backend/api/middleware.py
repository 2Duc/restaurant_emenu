from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from api.models import UserAccount
from api.services.table_token import verify_table_token

@database_sync_to_async
def _get_user(token):
    try:
        access = AccessToken(token)
        return UserAccount.objects.get(id=access['user_id'], is_active=True)
    except (InvalidToken, TokenError, UserAccount.DoesNotExist, KeyError):
        return AnonymousUser()

@database_sync_to_async
def _get_table_id(token):
    return verify_table_token(token)


class JwtAuthMiddleware:
    def __init__(self, inner): self.inner = inner
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get('query_string', b'').decode())
        token = query.get('token', [None])[0]
        scope = dict(scope)
        scope['user'] = await _get_user(token) if token else AnonymousUser()
        # WS-02: nếu không phải JWT nhân viên thì thử coi là token phiên bàn (khách).
        scope['table_id'] = None
        if token and not scope['user'].is_authenticated:
            scope['table_id'] = await _get_table_id(token)
        return await self.inner(scope, receive, send)

def JwtAuthMiddlewareStack(inner): return JwtAuthMiddleware(inner)
