"""Unit test cho api/services/qr_service.py."""
import base64
import io

from django.test import SimpleTestCase
from PIL import Image

from ..services.qr_service import qr_data_uri


def decode(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1])))


class QrDataUriTests(SimpleTestCase):
    def test_returns_png_data_uri(self):
        """Kết quả là data URI PNG decode được thành ảnh."""
        uri = qr_data_uri('http://x/table/1')
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        self.assertEqual(decode(uri).format, 'PNG')

    def test_box_size_and_border_change_image_size(self):
        """box_size lớn hơn -> ảnh lớn hơn."""
        self.assertGreater(decode(qr_data_uri('a', box_size=10)).size[0], decode(qr_data_uri('a', box_size=3)).size[0])

    def test_long_text_still_encodes(self):
        """URL VNPay dài ~2000 ký tự với long_text=True vẫn sinh được ảnh."""
        self.assertEqual(decode(qr_data_uri('https://x/?' + 'a=1&' * 500, long_text=True)).format, 'PNG')

    def test_unicode_text(self):
        """Chuỗi tiếng Việt không gây lỗi."""
        self.assertTrue(qr_data_uri('Bàn số 5 — ABC Restaurant').startswith('data:image/png'))

    def test_different_text_gives_different_image(self):
        """Hai nội dung khác nhau -> ảnh khác nhau; cùng nội dung -> giống nhau."""
        self.assertNotEqual(qr_data_uri('a'), qr_data_uri('b'))
        self.assertEqual(qr_data_uri('a'), qr_data_uri('a'))
