from decimal import Decimal

from ..models import Order, OrderItem, Payment, Table

OPEN_STATUSES = (Order.Status.PENDING, Order.Status.CONFIRMED)


def promotion_base(order, promo):
    """Số tiền mà mã được áp dụng lên: cả đơn, hoặc riêng các dòng của món gắn với mã (BR-05)."""
    lines = OrderItem.objects.filter(order=order)
    if promo.menu_item_id:
        lines = lines.filter(menu_item_id=promo.menu_item_id)
    return sum((i.unit_price * i.quantity for i in lines), Decimal(0))


def compute_discount(order, promo):
    if not promo:
        return Decimal(0)
    base = promotion_base(order, promo)
    discount = base * (promo.value / 100) if promo.discount_type == 'percent' else promo.value
    return min(base, Decimal(discount)).quantize(Decimal(1))


def recalc_order(order):
    """Tính lại tạm tính / giảm giá / tổng từ các món hiện có (dùng khi thêm hoặc huỷ món).

    - Mã giảm theo % được tính lại theo phần tiền áp dụng mới (cả đơn hoặc riêng một món);
      mã giảm cố định giữ nguyên nhưng không vượt phần áp dụng.
    - Giao dịch đang chờ (tiền mặt hoặc link VNPay) được cập nhật số tiền để không thu sai.
    """
    subtotal = sum((i.unit_price * i.quantity for i in OrderItem.objects.filter(order=order)), Decimal(0))
    discount = compute_discount(order, order.promotion)
    order.subtotal_amount = subtotal
    order.discount_amount = discount
    order.total_amount = max(subtotal - discount, Decimal(0))
    order.save(update_fields=['subtotal_amount', 'discount_amount', 'total_amount', 'updated_at'])
    getattr(order, '_prefetched_objects_cache', {}).pop('items', None)

    pending = Payment.objects.filter(order=order, status=Payment.Status.PENDING).first()
    if pending and pending.amount != order.total_amount:
        pending.amount = order.total_amount
        if pending.method == Payment.Method.VNPAY:
            pending.pay_url = ''          # link cũ mang số tiền cũ → buộc tạo link mới
            pending.vnp_create_date = ''
        pending.save()
    return order


def release_table_if_idle(table, status=Table.Status.EMPTY):
    """Bàn không còn đơn mở → trả về trạng thái trống (huỷ đơn) hoặc đang dọn (thanh toán xong)."""
    if not Order.objects.filter(table=table, status__in=OPEN_STATUSES).exists():
        table.status = status
        table.save(update_fields=['status'])
        return True
    return False
