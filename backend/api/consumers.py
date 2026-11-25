from channels.generic.websocket import AsyncJsonWebsocketConsumer

KITCHEN_ROLES = ('BEP', 'QL', 'AD')
STAFF_ROLES = ('PV', 'QL', 'AD')


def _allowed(user, roles):
    return bool(user and user.is_authenticated and (user.is_superuser or user.role in roles))


class RestaurantConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.group_name = self.scope['url_route']['kwargs']['group_name']
        user = self.scope.get('user')
        if self.group_name == 'kitchen_orders' and not _allowed(user, KITCHEN_ROLES):
            await self.close(code=4403); return
        if self.group_name == 'staff_orders' and not _allowed(user, STAFF_ROLES):
            await self.close(code=4403); return
        if self.group_name not in ('kitchen_orders', 'staff_orders') and not self.group_name.startswith('table_'):
            await self.close(); return
        if self.group_name.startswith('table_'):
            # WS-02: nhân viên (JWT) vào mọi bàn; khách phải có token phiên bàn hợp lệ ĐÚNG bàn này.
            is_staff = _allowed(user, ('PV', 'BEP', 'QL', 'AD'))
            if not is_staff and str(self.scope.get('table_id')) != self.group_name[len('table_'):]:
                await self.close(code=4403); return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def new_order(self, event):
        await self.send_json({'type': 'new_order', 'order': event['order']})

    async def item_status_updated(self, event):
        await self.send_json({'type': 'item_status_updated', 'order_item': event['order_item']})

    async def order_updated(self, event):
        await self.send_json({'type': 'order_updated', 'order': event['order']})

    async def staff_call(self, event):
        await self.send_json({'type': 'staff_call', 'call': event['call']})

    async def table_updated(self, event):
        await self.send_json({'type': 'table_updated', 'table': event['table']})

    async def menu_updated(self, event):
        await self.send_json({'type': 'menu_updated', 'menu_item': event['menu_item']})
