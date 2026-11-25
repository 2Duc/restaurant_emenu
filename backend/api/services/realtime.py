from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

STAFF_GROUPS = ('kitchen_orders', 'staff_orders')


def _send(groups, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    for group in groups:
        async_to_sync(layer.group_send)(group, payload)


def _after_commit(func):
    """BR-04: đẩy sự kiện sau khi giao dịch CSDL đã ghi xong để client tải lại thấy dữ liệu mới."""
    transaction.on_commit(func)


def broadcast_new_order(order):
    from ..serializers import OrderSerializer
    _after_commit(lambda: _send(
        (*STAFF_GROUPS, f'table_{order.table_id}'),
        {'type': 'new_order', 'order': OrderSerializer(order).data},
    ))


def broadcast_order_updated(order):
    """Báo cho bếp, nhân viên và khách của bàn biết đơn vừa đổi (thanh toán, huỷ, giảm giá...)."""
    from ..models import Order
    from ..serializers import OrderSerializer

    def send():
        fresh = Order.objects.select_related('table', 'promotion').prefetch_related('items__menu_item__category').get(pk=order.pk)
        _send((*STAFF_GROUPS, f'table_{order.table_id}'), {'type': 'order_updated', 'order': OrderSerializer(fresh).data})
    _after_commit(send)


def broadcast_item_status(order_item):
    from ..serializers import OrderItemSerializer
    _after_commit(lambda: _send(
        (f'table_{order_item.order.table_id}', *STAFF_GROUPS),
        {'type': 'item_status_updated', 'order_item': OrderItemSerializer(order_item).data},
    ))


def broadcast_staff_call(call):
    from ..serializers import StaffCallSerializer
    _after_commit(lambda: _send(
        ('staff_orders', f'table_{call.table_id}'),
        {'type': 'staff_call', 'call': StaffCallSerializer(call).data},
    ))


def broadcast_table_updated(table):
    from ..serializers import TableSerializer
    _after_commit(lambda: _send(
        ('staff_orders', f'table_{table.id}'),
        {'type': 'table_updated', 'table': TableSerializer(table).data},
    ))


def broadcast_menu_updated(menu_item):
    from ..serializers import MenuItemSerializer
    _after_commit(lambda: _send(
        STAFF_GROUPS,
        {'type': 'menu_updated', 'menu_item': MenuItemSerializer(menu_item).data},
    ))
