from rest_framework import serializers
from .services.qr_service import qr_data_uri
from .services.vietqr import build_vietqr_payload
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist
from .models import Category, MenuItem, Table, Order, OrderItem, Payment, Promotion, Review, UserAccount, StaffCall, AuditLog, SystemSetting

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'sort_order']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Tên danh mục không được để trống.')
        qs = Category.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Danh mục đã tồn tại.')
        return value

class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    avg_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'price', 'image_url', 'description', 'is_available', 'category', 'category_name', 'avg_rating', 'review_count']

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Giá món phải lớn hơn 0.')
        return value

    def validate_image_url(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Ảnh món tối đa 5MB.')
        return value

    def get_avg_rating(self, obj):
        value = getattr(obj, 'avg_rating_value', None)
        return round(float(value), 1) if value is not None else None
    def get_review_count(self, obj):
        return getattr(obj, 'review_count_value', 0) or 0

class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ['id', 'number', 'area', 'capacity', 'status', 'qr_code_url']
        read_only_fields = ['number', 'qr_code_url']  # số bàn = id bàn, tự gán khi lưu; QR sinh ở /tables/<id>/qr/

    def validate_capacity(self, value):
        if not 1 <= value <= 50:
            raise serializers.ValidationError('Sức chứa phải từ 1 đến 50.')
        return value

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    menu_item_image = serializers.ImageField(source='menu_item.image_url', read_only=True)
    category = serializers.IntegerField(source='menu_item.category_id', read_only=True)
    category_name = serializers.CharField(source='menu_item.category.name', read_only=True, default=None)
    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'menu_item', 'menu_item_name', 'menu_item_image', 'category', 'category_name', 'quantity', 'note', 'status', 'unit_price']
        read_only_fields = ['order', 'unit_price', 'status']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    table_number = serializers.CharField(source='table.number', read_only=True)
    promotion_code = serializers.CharField(source='promotion.code', read_only=True, allow_null=True)
    payment_id = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = ['id', 'table', 'table_number', 'status', 'subtotal_amount', 'discount_amount', 'total_amount', 'promotion', 'promotion_code', 'payment_id', 'payment_status', 'payment_method', 'created_by', 'created_at', 'updated_at', 'items']
        read_only_fields = fields

    def _payment(self, obj):
        try:
            return obj.payment
        except ObjectDoesNotExist:
            return None
    def get_payment_id(self, obj):
        p = self._payment(obj); return p.id if p else None
    def get_payment_status(self, obj):
        p = self._payment(obj); return p.status if p else None
    def get_payment_method(self, obj):
        p = self._payment(obj); return p.method if p else None

class OrderItemLiteSerializer(serializers.ModelSerializer):
    """Dòng món gọn cho danh sách đơn (bỏ ảnh, tên danh mục, khoá order)."""
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    category = serializers.IntegerField(source='menu_item.category_id', read_only=True)
    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_name', 'category', 'quantity', 'note', 'status', 'unit_price']
        read_only_fields = fields

class OrderListSerializer(OrderSerializer):
    """Đơn gọn cho danh sách (?page / ?active): không có created_by, items gọn."""
    items = OrderItemLiteSerializer(many=True, read_only=True)
    class Meta(OrderSerializer.Meta):
        fields = ['id', 'table', 'table_number', 'status', 'subtotal_amount', 'discount_amount', 'total_amount', 'promotion', 'promotion_code', 'payment_id', 'payment_status', 'payment_method', 'created_at', 'updated_at', 'items']
        read_only_fields = fields

class OrderCreateSerializer(serializers.Serializer):
    table_id = serializers.IntegerField()
    items = serializers.ListField(child=serializers.DictField())
    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('Đơn hàng phải có ít nhất một món.')
        for item in items:
            try:
                menu_id = int(item.get('menu_item_id'))
                quantity = int(item.get('quantity', 1))
            except (TypeError, ValueError):
                raise serializers.ValidationError('Mã món và số lượng phải hợp lệ.')
            if menu_id <= 0 or quantity < 1 or quantity > 99:
                raise serializers.ValidationError('Số lượng mỗi món phải từ 1 đến 99.')
            item['menu_item_id'], item['quantity'] = menu_id, quantity
            item['note'] = str(item.get('note') or '').strip()[:255]
        return items

class OrderItemStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['pending', 'cooking', 'done', 'served'])

class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    method = serializers.ChoiceField(choices=['vnpay', 'cash', 'bank_transfer'])  # vnpay = cổng VNPay; bank_transfer = chuyển khoản thủ công

class PaymentQuerySerializer(serializers.Serializer):
    order_id = serializers.IntegerField(required=False)
    payment_id = serializers.IntegerField(required=False)
    def validate(self, attrs):
        if not attrs.get('order_id') and not attrs.get('payment_id'):
            raise serializers.ValidationError('Cần nhập mã đơn hàng hoặc mã giao dịch.')
        return attrs

class PaymentRefundSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    amount = serializers.IntegerField(required=False, min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=200)

class PaymentSerializer(serializers.ModelSerializer):
    table_id = serializers.IntegerField(source='order.table_id', read_only=True)
    qr_image = serializers.SerializerMethodField()
    bank_info = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'order', 'table_id', 'method', 'amount', 'status', 'transaction_id', 'pay_url', 'qr_image',
                  'created_at', 'paid_at', 'vnp_transaction_no', 'vnp_response_code', 'vnp_bank_code',
                  'vnp_pay_date', 'refunded_amount', 'bank_info']

    def _is_pending_bank(self, obj):
        return obj.method == Payment.Method.BANK_TRANSFER and obj.status == Payment.Status.PENDING

    def get_bank_info(self, obj):
        # Chuyển khoản thủ công: thông tin tài khoản nhận + nội dung chuyển khoản (= mã đơn) lấy từ cấu hình hệ thống.
        if not self._is_pending_bank(obj):
            return None
        cfg = SystemSetting.load()
        return {'bank_name': cfg.bank_name, 'account_no': cfg.bank_account_no, 'account_name': cfg.bank_account_name,
                'content': transfer_content(obj.order_id), 'amount': int(obj.amount)}

    def get_qr_image(self, obj):
        if self._is_pending_bank(obj):
            cfg = SystemSetting.load()
            if not cfg.bank_configured:
                return None
            payload = build_vietqr_payload(cfg.bank_bin, cfg.bank_account_no, int(obj.amount), transfer_content(obj.order_id))
            return qr_data_uri(payload, box_size=5, border=2)
        # Mã QR do backend sinh từ link thanh toán VNPay; chỉ có khi đang chờ chuyển khoản.
        if obj.method == Payment.Method.VNPAY and obj.status == Payment.Status.PENDING and obj.pay_url:
            return qr_data_uri(obj.pay_url, box_size=5, border=2, long_text=True)
        return None

class PromotionSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True, default=None)

    class Meta:
        model = Promotion
        fields = ['id', 'code', 'discount_type', 'value', 'start_date', 'end_date', 'is_active', 'menu_item', 'menu_item_name']

    def validate_code(self, value):
        value = value.strip().upper()
        if not value.replace('-', '').replace('_', '').isalnum():
            raise serializers.ValidationError('Mã chỉ gồm chữ, số, dấu - hoặc _.')
        return value

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        kind = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        if start and end and end <= start:
            raise serializers.ValidationError('Ngày kết thúc phải sau ngày bắt đầu.')
        if value is not None and value <= 0:
            raise serializers.ValidationError('Giá trị giảm phải lớn hơn 0.')
        if kind == 'percent' and value is not None and value > 100:
            raise serializers.ValidationError('Giảm theo phần trăm không được vượt quá 100.')
        return attrs

class ReviewSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='order_item.menu_item.name', read_only=True)
    menu_item = serializers.IntegerField(source='order_item.menu_item_id', read_only=True)
    order = serializers.IntegerField(source='order_item.order_id', read_only=True)
    table_id = serializers.IntegerField(source='order_item.order.table_id', read_only=True)
    class Meta:
        model = Review
        fields = ['id', 'order_item', 'menu_item', 'menu_item_name', 'order', 'table_id', 'rating', 'comment', 'created_at']
        read_only_fields = ['created_at']
    def validate_order_item(self, value):
        if value.status != 'served' or value.order.status != 'completed':
            raise serializers.ValidationError('Chỉ được đánh giá món đã phục vụ trong đơn đã hoàn tất.')
        return value
    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Đánh giá phải từ 1 đến 5 sao.')
        return value

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAccount
        fields = ['id', 'username', 'role', 'is_active', 'is_superuser']

class StaffCallSerializer(serializers.ModelSerializer):
    table_number = serializers.CharField(source='table.number', read_only=True)
    class Meta:
        model = StaffCall
        fields = ['id', 'table', 'table_number', 'message', 'status', 'created_at', 'handled_by']
        read_only_fields = ['status', 'created_at', 'handled_by']

    def validate_message(self, value):
        return value.strip()[:255]


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, style={'input_type': 'password'})

    class Meta:
        model = UserAccount
        fields = ['id', 'username', 'first_name', 'email', 'role', 'is_active', 'last_login', 'password']
        read_only_fields = ['last_login']

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_role(self, value):
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        is_admin = bool(actor and (actor.is_superuser or actor.role == 'AD'))
        if value == 'AD' and not is_admin:
            raise serializers.ValidationError('Chỉ quản trị viên mới tạo / cấp quyền quản trị viên.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        if self.instance is not None and (self.instance.role == 'AD' or self.instance.is_superuser)                 and not (actor and (actor.is_superuser or actor.role == 'AD')):
            raise serializers.ValidationError({'detail': 'Chỉ quản trị viên mới sửa được tài khoản quản trị viên.'})
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Cần nhập mật khẩu cho tài khoản mới.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = UserAccount(**validated_data)
        user.is_staff = user.role in ('QL', 'AD')
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if 'role' in validated_data:
            instance.is_staff = instance.role in ('QL', 'AD')
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'actor_name', 'acted_mode', 'action', 'title', 'payload', 'created_at']


class ReauthSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, self.context['request'].user)
        return value


def transfer_content(order_id):
    """Nội dung chuyển khoản = mã đơn (chữ + số, không dấu để mọi ngân hàng chấp nhận)."""
    return f'DON{order_id}'


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = ['cash_enabled', 'bank_transfer_enabled', 'vnpay_enabled', 'bank_bin', 'bank_name', 'bank_account_no',
                  'bank_account_name', 'staff_call_cooldown_minutes', 'invoice_note', 'updated_at']
        read_only_fields = ['updated_at']

    def validate_bank_bin(self, v):
        v = v.strip()
        if v and not (v.isdigit() and len(v) == 6):
            raise serializers.ValidationError('Mã BIN ngân hàng gồm đúng 6 chữ số.')
        return v

    def validate_bank_account_no(self, v):
        v = v.strip().replace(' ', '')
        if v and not (v.isdigit() and 6 <= len(v) <= 19):
            raise serializers.ValidationError('Số tài khoản gồm 6–19 chữ số.')
        return v

    def validate_bank_account_name(self, v):
        return v.strip().upper()

    def validate_bank_name(self, v):
        return v.strip()

    def validate_staff_call_cooldown_minutes(self, v):
        if not 1 <= v <= 30:
            raise serializers.ValidationError('Thời gian chống spam từ 1 đến 30 phút.')
        return v

    def validate(self, attrs):
        cur = self.instance
        def val(k):
            return attrs.get(k, getattr(cur, k, ''))
        if val('bank_transfer_enabled') and any(k in attrs for k in ('bank_bin', 'bank_account_no', 'bank_account_name', 'bank_transfer_enabled')):
            filled = [bool(val(k)) for k in ('bank_bin', 'bank_account_no', 'bank_account_name')]
            if any(filled) and not all(filled):
                raise serializers.ValidationError('Cần nhập đủ mã BIN, số tài khoản và chủ tài khoản.')
        return attrs
