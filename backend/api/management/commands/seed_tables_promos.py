from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from api.models import MenuItem, Promotion, Table


def _area(n):
    if n <= 12:
        return 'Khu A'
    if n <= 24:
        return 'Khu B'
    return 'Sân vườn'


class Command(BaseCommand):
    help = 'Thêm bàn 1-30 còn thiếu và khuyến mãi mẫu (idempotent, không sửa dữ liệu có sẵn).'

    @transaction.atomic
    def handle(self, *args, **opts):
        caps = [2, 4, 4, 6]
        made = 0
        for n in range(1, 31):
            # Table.save gán number = pk nên tạo với pk tường minh.
            _, created = Table.objects.get_or_create(
                pk=n, defaults={'area': _area(n), 'capacity': caps[n % 4], 'status': Table.Status.EMPTY})
            made += created
        # Đồng bộ sequence để bàn tạo sau không trùng id.
        with connection.cursor() as c:
            if connection.vendor == 'postgresql':
                c.execute("SELECT setval(pg_get_serial_sequence('api_table','id'), GREATEST((SELECT MAX(id) FROM api_table), 30))")

        now = timezone.now()
        items = list(MenuItem.objects.filter(is_available=True).order_by('id')[:2])
        specs = [
            ('ABC10', 'percent', 10, now - timedelta(days=1), now + timedelta(days=180), True, None),
            ('GIAM50K', 'fixed', 50000, now - timedelta(days=1), now + timedelta(days=180), True, None),
            ('HETHAN20', 'percent', 20, now - timedelta(days=60), now - timedelta(days=30), True, None),
            ('SAPRA15', 'percent', 15, now + timedelta(days=30), now + timedelta(days=90), False, None),
        ]
        if items:
            specs.append(('MON15', 'percent', 15, now - timedelta(days=1), now + timedelta(days=90), True, items[0]))
            specs.append(('MON10K', 'fixed', 10000, now - timedelta(days=1), now + timedelta(days=90), True, items[-1]))
        pmade = 0
        for code, kind, val, s, e, act, item in specs:
            _, created = Promotion.objects.get_or_create(code=code, defaults={
                'discount_type': kind, 'value': val, 'start_date': s, 'end_date': e,
                'is_active': act, 'menu_item': item})
            pmade += created
        self.stdout.write(f'Tables created: {made} (total {Table.objects.count()}); promos created: {pmade} (total {Promotion.objects.count()})')
