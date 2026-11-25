import secrets

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import AbstractUser


class UserAccount(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'AD', 'Quản trị viên'
        MANAGER = 'QL', 'Quản lý'
        WAITER = 'PV', 'Nhân viên phục vụ'
        KITCHEN = 'BEP', 'Bộ phận bếp'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.WAITER)


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='menu_items', null=True, blank=True)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=0)
    image_url = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    description = models.TextField(blank=True)
    is_available = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


def new_qr_token():
    return secrets.token_urlsafe(24)


class Table(models.Model):
    class Status(models.TextChoices):
        EMPTY = 'empty', 'Trống'
        OCCUPIED = 'occupied', 'Đang sử dụng'
        CLEANING = 'cleaning', 'Đang dọn'

    # Số bàn chính là id của bàn (tự gán khi lưu) — xem Table.save().
    number = models.CharField(max_length=20, unique=True, blank=True)
    area = models.CharField(max_length=50, blank=True)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EMPTY)
    qr_code_url = models.URLField(max_length=300, blank=True, null=True)
    # AUTH-05: mã bí mật nằm trong link QR (?k=); đổi mã = QR cũ và mọi phiên bàn đang mở mất hiệu lực.
    qr_token = models.CharField(max_length=64, unique=True, default=new_qr_token, editable=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mỗi bàn có 1 id, id đó dùng làm số bàn và nằm trên đường link QR (/table/<id>).
        if self.number != str(self.pk):
            self.number = str(self.pk)
            super().save(update_fields=['number'])

    def __str__(self):
        return f'Bàn {self.pk}'


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ xử lý'
        CONFIRMED = 'confirmed', 'Đã xác nhận'
        COMPLETED = 'completed', 'Hoàn thành'
        CANCELLED = 'cancelled', 'Đã hủy'

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    subtotal_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    promotion = models.ForeignKey('Promotion', null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    # ERD: USER creates ORDER — để trống khi khách tự đặt qua QR, có giá trị khi nhân viên gọi món hộ.
    created_by = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['table', 'status'])]

    def __str__(self):
        return f'Đơn #{self.pk} - bàn {self.table_id}'

    def payment_status_is_success(self):
        return Payment.objects.filter(order=self, status__in=['success', 'refunded']).exists()


class OrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ chế biến'
        COOKING = 'cooking', 'Đang chế biến'
        DONE = 'done', 'Đã hoàn thành'
        SERVED = 'served', 'Đã phục vụ'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField(default=1)
    note = models.CharField(max_length=255, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Tiền mặt'
        MOMO = 'momo', 'MoMo'
        VNPAY = 'vnpay', 'Chuyển khoản (VNPay)'
        BANK_TRANSFER = 'bank_transfer', 'Chuyển khoản ngân hàng'
        ZALOPAY = 'zalopay', 'ZaloPay'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ thanh toán'
        SUCCESS = 'success', 'Thành công'
        FAILED = 'failed', 'Thất bại'
        REFUNDED = 'refunded', 'Đã hoàn tiền'

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_id = models.CharField(max_length=100, unique=True)  # = vnp_TxnRef
    # URL VNPay dài hơn 200 ký tự nên không dùng URLField mặc định.
    pay_url = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Dữ liệu VNPay (tương đương model Payment_VNPay trong dự án mẫu)
    vnp_create_date = models.CharField(max_length=14, blank=True, default='')
    vnp_transaction_no = models.CharField(max_length=30, blank=True, default='')
    vnp_response_code = models.CharField(max_length=5, blank=True, default='')
    vnp_bank_code = models.CharField(max_length=30, blank=True, default='')
    vnp_pay_date = models.CharField(max_length=14, blank=True, default='')
    refunded_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)


class Promotion(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Phần trăm'
        FIXED = 'fixed', 'Số tiền cố định'

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=12, decimal_places=0)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    # BR-05: áp dụng cho cả đơn (để trống) hoặc riêng một món.
    menu_item = models.ForeignKey('MenuItem', null=True, blank=True, on_delete=models.CASCADE, related_name='promotions')

    def __str__(self):
        return self.code


class Review(models.Model):
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class StaffCall(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ tiếp nhận'
        ACCEPTED = 'accepted', 'Đang xử lý'
        RESOLVED = 'resolved', 'Đã hoàn thành'

    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='staff_calls')
    message = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_by = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['status', '-created_at']

    def __str__(self):
        return f'Call {self.table.number} - {self.status}'


class SystemSetting(models.Model):
    """Cấu hình hệ thống (singleton pk=1) do Admin chỉnh. Bí mật VNPay KHÔNG lưu ở đây (chỉ đọc từ env)."""
    cash_enabled = models.BooleanField(default=True)
    bank_transfer_enabled = models.BooleanField(default=True)
    vnpay_enabled = models.BooleanField(default=True)
    bank_bin = models.CharField(max_length=6, blank=True, help_text='Mã BIN ngân hàng (NAPAS), 6 chữ số')
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_no = models.CharField(max_length=19, blank=True)
    bank_account_name = models.CharField(max_length=100, blank=True)
    staff_call_cooldown_minutes = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(30)])
    invoice_note = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    def __str__(self):
        return 'Cấu hình hệ thống'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        kwargs['force_insert'] = False   # singleton: luôn ghi đè bản ghi pk=1
        super().save(*args, **kwargs)

    @property
    def bank_configured(self):
        return bool(self.bank_bin and self.bank_account_no and self.bank_account_name)


class AuditLog(models.Model):
    """Nhật ký thao tác của quản lý (acted_by / acted_mode) — hiển thị ở ngăn "Nhật ký Audit"."""
    actor = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')
    actor_name = models.CharField(max_length=150, blank=True)
    acted_mode = models.CharField(max_length=20, default='manager')
    action = models.CharField(max_length=40)
    title = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} by {self.actor_name}'
