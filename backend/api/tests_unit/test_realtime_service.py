"""Unit test cho api/services/realtime.py (BR-04: chỉ đẩy sau khi commit)."""
from decimal import Decimal
from unittest import mock

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from ..models import MenuItem, Order, OrderItem, StaffCall, Table
from ..services import realtime


class BroadcastAfterCommitTests(TestCase):
    """TestCase bọc trong transaction -> dùng captureOnCommitCallbacks để mô phỏng commit."""

    def setUp(self):
        self.table = Table.objects.create()
        self.order = Order.objects.create(table=self.table)

    def fire(self, func, *args):
        with mock.patch.object(realtime, '_send') as send:
            with self.captureOnCommitCallbacks(execute=True):
                func(*args)
        return send

    def test_nothing_sent_before_commit(self):
        """Chưa commit thì không gọi group_send."""
        with mock.patch.object(realtime, '_send') as send:
            realtime.broadcast_new_order(self.order)
            send.assert_not_called()

    def test_new_order_sent_to_staff_and_table_groups_on_commit(self):
        """Sau commit: gửi tới kitchen_orders, staff_orders và table_<id>."""
        send = self.fire(realtime.broadcast_new_order, self.order)
        groups, payload = send.call_args.args
        self.assertEqual(set(groups), {'kitchen_orders', 'staff_orders', f'table_{self.table.id}'})
        self.assertEqual((payload['type'], payload['order']['id']), ('new_order', self.order.id))

    def test_order_updated_reloads_fresh_data(self):
        """order_updated đọc lại đơn từ DB tại thời điểm commit."""
        with mock.patch.object(realtime, '_send') as send:
            with self.captureOnCommitCallbacks(execute=True):
                realtime.broadcast_order_updated(self.order)
                Order.objects.filter(pk=self.order.pk).update(status='confirmed')
        self.assertEqual(send.call_args.args[1]['order']['status'], 'confirmed')

    def test_staff_call_groups(self):
        """staff_call chỉ tới staff_orders và bàn đó."""
        call = StaffCall.objects.create(table=self.table, message='nước')
        send = self.fire(realtime.broadcast_staff_call, call)
        self.assertEqual(send.call_args.args[0], ('staff_orders', f'table_{self.table.id}'))
        self.assertEqual(send.call_args.args[1]['type'], 'staff_call')

    def test_table_updated_groups(self):
        """table_updated tới staff_orders và bàn đó."""
        send = self.fire(realtime.broadcast_table_updated, self.table)
        self.assertEqual(send.call_args.args[0], ('staff_orders', f'table_{self.table.id}'))
        self.assertEqual(send.call_args.args[1]['table']['id'], self.table.id)

    def test_menu_updated_goes_to_staff_groups_only(self):
        """menu_updated chỉ tới nhóm nhân viên."""
        item = MenuItem.objects.create(name='A', price=Decimal(1000))
        send = self.fire(realtime.broadcast_menu_updated, item)
        self.assertEqual(send.call_args.args[0], realtime.STAFF_GROUPS)

    def test_item_status_includes_table_group(self):
        """item_status_updated tới bàn + nhân viên."""
        item = MenuItem.objects.create(name='A', price=Decimal(1000))
        oi = OrderItem.objects.create(order=self.order, menu_item=item, unit_price=item.price)
        send = self.fire(realtime.broadcast_item_status, oi)
        self.assertIn(f'table_{self.table.id}', send.call_args.args[0])
        self.assertEqual(send.call_args.args[1]['type'], 'item_status_updated')


class SendTests(TestCase):
    def test_send_calls_group_send_for_each_group(self):
        """_send gọi layer.group_send một lần cho mỗi nhóm."""
        calls = []

        class Layer:
            async def group_send(self, group, payload):
                calls.append((group, payload))
        with mock.patch.object(realtime, 'get_channel_layer', return_value=Layer()):
            realtime._send(('a', 'b'), {'type': 'x'})
        self.assertEqual(calls, [('a', {'type': 'x'}), ('b', {'type': 'x'})])

    def test_send_without_layer_is_noop(self):
        """Không có channel layer -> bỏ qua, không lỗi."""
        with mock.patch.object(realtime, 'get_channel_layer', return_value=None):
            realtime._send(('a',), {})


class RollbackTests(TransactionTestCase):
    def setUp(self):
        self.order = Order.objects.create(table=Table.objects.create())

    def test_nothing_sent_when_transaction_rolls_back(self):
        """Giao dịch bị rollback -> sự kiện không bao giờ được gửi."""
        with mock.patch.object(realtime, '_send') as send:
            try:
                with transaction.atomic():
                    realtime.broadcast_new_order(self.order)
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
            send.assert_not_called()

    def test_sent_once_when_transaction_commits(self):
        """Commit thật -> gửi đúng 1 lần, và chỉ sau khi thoát atomic."""
        with mock.patch.object(realtime, '_send') as send:
            with transaction.atomic():
                realtime.broadcast_new_order(self.order)
                send.assert_not_called()
            send.assert_called_once()
