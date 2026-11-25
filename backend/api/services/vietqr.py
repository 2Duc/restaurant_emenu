"""Sinh chuỗi VietQR (EMVCo / NAPAS 247) chuyển khoản tới tài khoản ngân hàng."""
import re
import unicodedata


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) — dạng HEX 4 ký tự in hoa."""
    crc = 0xFFFF
    for byte in data.encode('ascii'):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f'{crc:04X}'


def _tlv(tag: str, value: str) -> str:
    return f'{tag}{len(value):02d}{value}'


def ascii_text(value: str, max_len: int = 25) -> str:
    """Bỏ dấu, chỉ giữ chữ-số-khoảng trắng để nội dung chuyển khoản hợp lệ trong EMV."""
    text = unicodedata.normalize('NFD', value or '').replace('đ', 'd').replace('Đ', 'D')
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^A-Za-z0-9 ]', '', text)[:max_len]


def build_vietqr_payload(bin_code: str, account_no: str, amount: int, content: str) -> str:
    """QR động (Point of Initiation 12), dịch vụ chuyển nhanh tới tài khoản (QRIBFTTA), tiền tệ VND (704)."""
    beneficiary = _tlv('00', bin_code) + _tlv('01', account_no)
    merchant = _tlv('00', 'A000000727') + _tlv('01', beneficiary) + _tlv('02', 'QRIBFTTA')
    body = (_tlv('00', '01') + _tlv('01', '12') + _tlv('38', merchant) + _tlv('53', '704')
            + _tlv('54', str(int(amount))) + _tlv('58', 'VN')
            + _tlv('62', _tlv('08', ascii_text(content))))
    body += '6304'
    return body + crc16_ccitt(body)


def verify_crc(payload: str) -> bool:
    return len(payload) > 4 and payload[-8:-4] == '6304' and crc16_ccitt(payload[:-4]) == payload[-4:]
