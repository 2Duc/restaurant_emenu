import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import Category, MenuItem, Table, Promotion
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Tạo dữ liệu demo cho ABC Restaurant (idempotent).'
    def handle(self, *args, **options):
        categories = {}
        for name in ['Khai vị', 'Món chính', 'Món chay', 'Đồ uống', 'Tráng miệng']:
            categories[name], _ = Category.objects.get_or_create(name=name)
        dishes = [
            ('Phở bò tái', 'Món chính', 85000, 'Phở bò truyền thống, nước dùng ninh xương.'),
            ('Chả giò hải sản', 'Khai vị', 75000, 'Chả giò giòn nhân hải sản.'),
            ('Gỏi cuốn tôm thịt', 'Khai vị', 60000, 'Gỏi cuốn tươi kèm nước chấm.'),
            ('Cơm chiên hải sản', 'Món chính', 110000, 'Cơm chiên với tôm và mực.'),
            ('Nấm đùi gà kho tiêu', 'Món chay', 70000, 'Nấm kho tiêu xanh.'),
            ('Trà sen vàng', 'Đồ uống', 45000, 'Trà sen và long nhãn.'),
            ('Trà đào cam sả', 'Đồ uống', 42000, 'Trà đào cam sả mát lạnh.'),
            ('Chè khúc bạch', 'Tráng miệng', 50000, 'Chè khúc bạch hạnh nhân.'),
        ]
        for name, cat, price, desc in dishes:
            MenuItem.objects.get_or_create(name=name, defaults={'category':categories[cat], 'price':Decimal(price), 'description':desc, 'is_available':True})
        for i in range(1, 25):
            Table.objects.get_or_create(pk=i, defaults={'area':'Khu A' if i<=12 else 'Khu B', 'capacity':4})  # số bàn = id (Table.save tự gán)
        now=timezone.now()
        Promotion.objects.get_or_create(code='ABC10', defaults={'discount_type':'percent','value':Decimal('10'),'start_date':now-timedelta(days=1),'end_date':now+timedelta(days=90),'is_active':True})
        password=os.getenv('SEED_DEMO_PASSWORD')
        if password:
            User=get_user_model()
            for username, role in [('manager_demo','QL'),('waiter_demo','PV'),('kitchen_demo','BEP')]:
                user,created=User.objects.get_or_create(username=username, defaults={'role':role,'is_staff':role=='QL'})
                if created: user.set_password(password); user.save()
        self.stdout.write(self.style.SUCCESS('Đã tạo dữ liệu demo: 24 bàn, danh mục, món ăn và voucher ABC10.'))
