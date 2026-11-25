"""Unit test cho serializers: Category, MenuItem, Table, OrderCreate, các serializer đơn giản."""
import io
from decimal import Decimal
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from .. import serializers as s
from ..models import Category, MenuItem


def errors(ser):
    ser.is_valid()
    return ser.errors


class CategorySerializerTests(TestCase):
    def test_blank_name_rejected(self):
        """Tên toàn khoảng trắng -> lỗi."""
        self.assertIn('name', errors(s.CategorySerializer(data={'name': '   '})))

    def test_duplicate_name_case_insensitive(self):
        """Trùng tên (không phân biệt hoa thường, ASCII; SQLite iexact không xử lý Unicode) -> lỗi."""
        Category.objects.create(name='Main dish')
        self.assertIn('name', errors(s.CategorySerializer(data={'name': 'MAIN DISH'})))

    def test_update_same_name_allowed(self):
        """Sửa chính danh mục đó giữ nguyên tên -> hợp lệ."""
        c = Category.objects.create(name='A')
        self.assertTrue(s.CategorySerializer(c, data={'name': 'A', 'sort_order': 2}).is_valid())

    def test_name_is_stripped(self):
        """Tên được cắt khoảng trắng đầu cuối."""
        ser = s.CategorySerializer(data={'name': '  Tráng miệng '})
        self.assertTrue(ser.is_valid())
        self.assertEqual(ser.validated_data['name'], 'Tráng miệng')


class MenuItemSerializerTests(TestCase):
    def data(self, **kw):
        return {'name': 'Phở', 'price': '85000', **kw}

    def test_negative_zero_and_non_numeric_price_rejected(self):
        """Giá âm, 0, không phải số -> lỗi trường price."""
        for bad in ('-1', '0', 'abc'):
            self.assertIn('price', errors(s.MenuItemSerializer(data=self.data(price=bad))), bad)

    def test_valid_price_accepted(self):
        """Giá dương hợp lệ."""
        self.assertTrue(s.MenuItemSerializer(data=self.data()).is_valid())

    def test_invalid_image_format_rejected(self):
        """File giả làm ảnh (nội dung không phải ảnh) -> lỗi image_url."""
        bad = SimpleUploadedFile('a.png', b'not an image', content_type='image/png')
        self.assertIn('image_url', errors(s.MenuItemSerializer(data=self.data(image_url=bad))))

    def test_oversize_image_rejected(self):
        """Ảnh > 5MB -> lỗi 'tối đa 5MB'."""
        big = SimpleNamespace(size=5 * 1024 * 1024 + 1)
        with self.assertRaisesMessage(s.serializers.ValidationError, '5MB'):
            s.MenuItemSerializer().validate_image_url(big)

    def test_image_exactly_5mb_accepted(self):
        """Biên: đúng 5MB vẫn hợp lệ."""
        ok = SimpleNamespace(size=5 * 1024 * 1024)
        self.assertIs(s.MenuItemSerializer().validate_image_url(ok), ok)

    def test_empty_image_accepted(self):
        """Không gửi ảnh -> hợp lệ."""
        self.assertIsNone(s.MenuItemSerializer().validate_image_url(None))

    def test_valid_png_accepted(self):
        """PNG thật nhỏ hợp lệ."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (4, 4), 'red').save(buf, format='PNG')
        f = SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')
        self.assertTrue(s.MenuItemSerializer(data=self.data(image_url=f)).is_valid())

    def test_rating_annotations(self):
        """Không có annotation -> avg None, count 0; có thì làm tròn 1 chữ số."""
        item = MenuItem(name='A', price=1)
        ser = s.MenuItemSerializer()
        self.assertEqual((ser.get_avg_rating(item), ser.get_review_count(item)), (None, 0))
        item.avg_rating_value, item.review_count_value = Decimal('4.26'), 3
        self.assertEqual((ser.get_avg_rating(item), ser.get_review_count(item)), (4.3, 3))


class TableSerializerTests(TestCase):
    def test_capacity_bounds(self):
        """Sức chứa: 0, 51, -3 sai; 1 và 50 đúng."""
        for cap, ok in ((0, False), (1, True), (50, True), (51, False), (-3, False)):
            self.assertEqual(s.TableSerializer(data={'capacity': cap, 'area': 'A'}).is_valid(), ok, cap)

    def test_number_is_read_only(self):
        """Client không đặt được number; sau khi lưu number = id."""
        ser = s.TableSerializer(data={'capacity': 4, 'number': '99'})
        self.assertTrue(ser.is_valid())
        t = ser.save()
        self.assertEqual(t.number, str(t.pk))


class OrderCreateSerializerTests(SimpleTestCase):
    def check(self, items):
        return s.OrderCreateSerializer(data={'table_id': 1, 'items': items})

    def test_empty_items_rejected(self):
        """Danh sách món rỗng -> lỗi."""
        self.assertIn('items', errors(self.check([])))

    def test_quantity_bounds(self):
        """Số lượng 0, 100, -1 sai; 1 và 99 đúng."""
        for q, ok in ((0, False), (1, True), (99, True), (100, False), (-1, False)):
            self.assertEqual(self.check([{'menu_item_id': 1, 'quantity': q}]).is_valid(), ok, q)

    def test_invalid_ids_rejected(self):
        """menu_item_id thiếu / không phải số / <= 0 -> lỗi."""
        for bad in ({}, {'menu_item_id': 'x'}, {'menu_item_id': 0}, {'menu_item_id': -2}):
            self.assertFalse(self.check([bad]).is_valid(), bad)

    def test_normalises_values_and_note(self):
        """Ép kiểu số, quantity mặc định 1, note cắt khoảng trắng và tối đa 255."""
        ser = self.check([{'menu_item_id': '2', 'note': ' ' + 'x' * 300}])
        self.assertTrue(ser.is_valid())
        item = ser.validated_data['items'][0]
        self.assertEqual((item['menu_item_id'], item['quantity'], len(item['note'])), (2, 1, 255))


class SimpleSerializerTests(SimpleTestCase):
    def test_item_status_choices(self):
        """Trạng thái món chỉ nhận 4 giá trị."""
        self.assertTrue(s.OrderItemStatusSerializer(data={'status': 'cooking'}).is_valid())
        self.assertFalse(s.OrderItemStatusSerializer(data={'status': 'cancelled'}).is_valid())

    def test_payment_create_methods(self):
        """Chỉ nhận vnpay / cash (không MoMo, ZaloPay)."""
        for m, ok in (('cash', True), ('vnpay', True), ('momo', False), ('zalopay', False)):
            self.assertEqual(s.PaymentCreateSerializer(data={'order_id': 1, 'method': m}).is_valid(), ok, m)

    def test_payment_query_requires_one_id(self):
        """Truy vấn cần order_id hoặc payment_id."""
        self.assertFalse(s.PaymentQuerySerializer(data={}).is_valid())
        self.assertTrue(s.PaymentQuerySerializer(data={'order_id': 1}).is_valid())
        self.assertTrue(s.PaymentQuerySerializer(data={'payment_id': 1}).is_valid())

    def test_refund_amount_min_1(self):
        """Hoàn tiền một phần phải >= 1; bỏ trống = hoàn toàn phần."""
        self.assertFalse(s.PaymentRefundSerializer(data={'payment_id': 1, 'amount': 0}).is_valid())
        self.assertTrue(s.PaymentRefundSerializer(data={'payment_id': 1, 'amount': 1}).is_valid())
        self.assertTrue(s.PaymentRefundSerializer(data={'payment_id': 1}).is_valid())

    def test_staff_call_message_trimmed(self):
        """Lời nhắn cắt khoảng trắng và tối đa 255 ký tự."""
        ser = s.StaffCallSerializer()
        self.assertEqual(ser.validate_message('  hi  '), 'hi')
        self.assertEqual(len(ser.validate_message('x' * 400)), 255)
