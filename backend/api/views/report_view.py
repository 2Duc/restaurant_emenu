from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Order, OrderItem, Payment
from ..permissions import IsManagerOrAdmin

PAID = (Payment.Status.SUCCESS, Payment.Status.REFUNDED)
PERIOD_DAYS = {'day': 1, 'week': 7, 'month': 30}


def _range(params):
    """BR-09: doanh thu theo ngày / tuần / tháng hoặc khoảng ngày tuỳ chọn (date_from, date_to: YYYY-MM-DD)."""
    today = timezone.localdate()
    try:
        d_from = datetime.strptime(params['date_from'], '%Y-%m-%d').date() if params.get('date_from') else None
        d_to = datetime.strptime(params['date_to'], '%Y-%m-%d').date() if params.get('date_to') else None
    except ValueError:
        d_from = d_to = None
    if d_from or d_to:
        d_to = d_to or today
        d_from = d_from or d_to
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        d_from = max(d_from, d_to - timedelta(days=365))
        period = 'custom'
    else:
        period = params.get('period') if params.get('period') in PERIOD_DAYS else 'month'
        d_to = today
        d_from = today - timedelta(days=PERIOD_DAYS[period] - 1)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(d_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(d_to, time.max), tz)
    return period, d_from, d_to, start, end


def _num(value):
    return int(value or 0)


class ReportSummaryAPIView(APIView):
    """GET /api/reports/summary/?period=day|week|month | ?date_from=&date_to=

    Doanh thu = giao dịch thành công (theo thời điểm thanh toán) trừ tiền đã hoàn — khớp với đơn đã thanh toán (AC-07).
    """
    permission_classes = [IsManagerOrAdmin]

    def get(self, request):
        period, d_from, d_to, start, end = _range(request.query_params)
        tz = timezone.get_current_timezone()
        paid = list(Payment.objects.filter(status__in=PAID, paid_at__gte=start, paid_at__lte=end)
                    .select_related('order').only('id', 'order_id', 'method', 'amount', 'refunded_amount', 'paid_at'))

        gross = sum((p.amount for p in paid), Decimal(0))
        refunded = sum((p.refunded_amount for p in paid), Decimal(0))
        revenue = gross - refunded
        paid_orders = len(paid)

        # Chuỗi doanh thu: theo giờ nếu xem 1 ngày, ngược lại theo ngày.
        single_day = d_from == d_to
        if single_day:
            buckets = {h: Decimal(0) for h in range(24)}
            for p in paid:
                buckets[timezone.localtime(p.paid_at, tz).hour] += p.amount - p.refunded_amount
            series = [{'label': f'{h}h', 'hour': h, 'total': _num(v)} for h, v in buckets.items()]
        else:
            days = (d_to - d_from).days + 1
            buckets = {d_from + timedelta(days=i): Decimal(0) for i in range(days)}
            for p in paid:
                buckets[timezone.localtime(p.paid_at, tz).date()] += p.amount - p.refunded_amount
            series = [{'label': d.strftime('%d/%m'), 'date': d.isoformat(), 'total': _num(v)} for d, v in buckets.items()]

        # Khung giờ cao điểm: số đơn đã thanh toán theo giờ đặt đơn.
        peak = {h: {'hour': h, 'orders': 0, 'total': 0} for h in range(24)}
        for p in paid:
            h = timezone.localtime(p.order.created_at, tz).hour
            peak[h]['orders'] += 1
            peak[h]['total'] += _num(p.amount - p.refunded_amount)

        order_ids = [p.order_id for p in paid]
        best = (OrderItem.objects.filter(order_id__in=order_ids)
                .values('menu_item_id', 'menu_item__name', 'menu_item__category__name')
                .annotate(qty=Sum('quantity'), rev=Sum(F('quantity') * F('unit_price')))
                .order_by('-qty', '-rev')[:10])

        methods = {}
        for p in paid:
            m = methods.setdefault(p.method, {'method': p.method, 'orders': 0, 'total': 0})
            m['orders'] += 1
            m['total'] += _num(p.amount - p.refunded_amount)

        return Response({
            'period': period,
            'date_from': d_from.isoformat(), 'date_to': d_to.isoformat(),
            'revenue': _num(revenue), 'gross': _num(gross), 'refunded': _num(refunded),
            'paid_orders': paid_orders,
            'avg_order': _num(revenue / paid_orders) if paid_orders else 0,
            'pending_orders': Order.objects.filter(status__in=['pending', 'confirmed']).count(),
            'cancelled_orders': Order.objects.filter(status='cancelled', updated_at__gte=start, updated_at__lte=end).count(),
            'series': series,
            'best_sellers': [{'id': b['menu_item_id'], 'name': b['menu_item__name'], 'category': b['menu_item__category__name'],
                              'quantity': _num(b['qty']), 'revenue': _num(b['rev'])} for b in best],
            'peak_hours': list(peak.values()),
            'methods': sorted(methods.values(), key=lambda m: -m['total']),
        })
