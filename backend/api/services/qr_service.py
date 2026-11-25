import base64
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M


def qr_data_uri(text: str, *, box_size: int = 6, border: int = 2, long_text: bool = False) -> str:
    """Sinh ảnh QR (PNG) từ chuỗi và trả về data URI để <img src=...> dùng trực tiếp.

    long_text=True dùng mức sửa lỗi thấp để mã QR của URL VNPay (rất dài) đỡ dày đặc.
    """
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_L if long_text else ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


# ---------------------------------------------------------------------------
# QR bàn lưu bền: sinh 1 lần, lưu file theo (qr_token, base URL), chỉ sinh lại khi token hoặc base đổi.
# Tên file chứa băm của token (không lộ token) và KHÔNG được công bố qua API công khai (ảnh chứa mã k).
# ---------------------------------------------------------------------------
import hashlib
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

BRAND = '#12805A'
BRAND_DEEP = '#0C5A40'
GOLD = '#CDB57A'
INK_2 = '#46605A'
CARD_W, CARD_H = 800, 1100
FONT_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'fonts' / 'PlusJakartaSans.ttf'


def qr_cache_dir():
    path = Path(settings.MEDIA_ROOT) / 'qr'
    path.mkdir(parents=True, exist_ok=True)
    return path


def table_link(table, base_url):
    return f'{base_url.rstrip("/")}/table/{table.pk}?k={table.qr_token}'


def _fingerprint(table, base_url):
    return hashlib.sha256(f'{table.qr_token}|{base_url.rstrip("/")}'.encode()).hexdigest()[:20]


def table_qr_file(table, base_url):
    """Đường dẫn file PNG QR của bàn cho (token, base). Chưa có thì sinh rồi lưu; xoá file cũ của bàn."""
    directory = qr_cache_dir()
    path = directory / f't{table.pk}_{_fingerprint(table, base_url)}.png'
    if not path.exists():
        qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=2)
        qr.add_data(table_link(table, base_url))
        qr.make(fit=True)
        tmp = path.with_suffix('.tmp')
        qr.make_image(fill_color='black', back_color='white').save(tmp, format='PNG')
        tmp.replace(path)
        for old in directory.glob(f't{table.pk}_*.png'):
            if old != path:
                old.unlink(missing_ok=True)
    return path


def table_qr_data_uri(table, base_url, size=None):
    img = Image.open(table_qr_file(table, base_url)).convert('RGB')
    if size:
        img = img.resize((size, size), Image.NEAREST)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def _font(size, weight=600):
    try:
        font = ImageFont.truetype(str(FONT_PATH), size)
        try:
            font.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001 - font tĩnh / thiếu FreeType: dùng mặc định
            pass
        return font
    except OSError:
        return ImageFont.load_default(size)


def _centered(draw, text, y, font, fill):
    width = draw.textlength(text, font=font)
    draw.text(((CARD_W - width) / 2, y), text, font=font, fill=fill)


def table_card_image(table, base_url):
    """Thẻ dán bàn: tên quán, số bàn, QR lớn, dòng hướng dẫn quét."""
    card = Image.new('RGB', (CARD_W, CARD_H), 'white')
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((12, 12, CARD_W - 12, CARD_H - 12), radius=40, outline=BRAND, width=8)
    _centered(draw, 'ABC Restaurant', 70, _font(54, 700), BRAND_DEEP)
    draw.line((CARD_W / 2 - 60, 160, CARD_W / 2 + 60, 160), fill=GOLD, width=5)
    _centered(draw, f'Bàn {table.pk}', 190, _font(120, 700), BRAND)
    qr = Image.open(table_qr_file(table, base_url)).convert('RGB').resize((560, 560), Image.NEAREST)
    card.paste(qr, ((CARD_W - 560) // 2, 360))
    _centered(draw, 'Quét mã để xem thực đơn', 960, _font(40, 600), BRAND_DEEP)
    _centered(draw, 'và gọi món tại bàn', 1012, _font(34, 500), INK_2)
    return card


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def cards_pages(tables, base_url):
    """Các trang A4 (150 dpi) dạng ảnh, 4 thẻ mỗi trang (2x2), cắt theo viền."""
    page_w, page_h = 1240, 1754
    cell_w, cell_h = 540, 743   # tỉ lệ thẻ 800:1100
    gap_x, gap_y = 40, 40
    left = (page_w - 2 * cell_w - gap_x) // 2
    top = (page_h - 2 * cell_h - gap_y) // 2
    pages = []
    for start in range(0, max(len(tables), 1), 4):
        page = Image.new('RGB', (page_w, page_h), 'white')
        for i, table in enumerate(tables[start:start + 4]):
            card = table_card_image(table, base_url).resize((cell_w, cell_h), Image.LANCZOS)
            page.paste(card, (left + (i % 2) * (cell_w + gap_x), top + (i // 2) * (cell_h + gap_y)))
        pages.append(page)
    return pages


def cards_pdf(tables, base_url):
    pages = cards_pages(tables, base_url)
    buffer = io.BytesIO()
    pages[0].save(buffer, format='PDF', save_all=True, append_images=pages[1:], resolution=150.0)
    return buffer.getvalue()
