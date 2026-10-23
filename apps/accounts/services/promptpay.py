import io
import base64
import hashlib
from decimal import Decimal
from django.conf import settings
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask

def generate_promptpay_payload(target: str, amount: float | Decimal | None = None) -> str:
    """
    Generate EMVCo QR code standard payload for PromptPay.
    Supports Thailand PromptPay Mobile (10 digits) or Tax ID / National ID (13 digits).
    Can lock amount (Dynamic QR - tag 01=12).
    """
    target = target.replace('-', '').strip()
    if len(target) == 10 and target.startswith('0'):
        # Mobile: Country code 66 replacing leading 0
        target_formatted = '0066' + target[1:]
        sub_tag = '01'
    elif len(target) == 13:
        target_formatted = target
        sub_tag = '02'
    else:
        target_formatted = target
        sub_tag = '03'

    aid = 'A000000677010111'
    merchant_data = f'00{len(aid):02d}{aid}{sub_tag}{len(target_formatted):02d}{target_formatted}'

    # Tag 00: Payload Format Indicator ("01")
    # Tag 01: Point of Initiation Method (12 = Dynamic QR with fixed amount, 11 = Static)
    payload = '000201'
    payload += '010212' if amount is not None else '010211'
    payload += f'29{len(merchant_data):02d}{merchant_data}'
    payload += '5303764'  # Currency: 764 (THB)

    if amount is not None:
        amount_val = Decimal(str(amount))
        amt_str = f'{amount_val:.2f}'
        payload += f'54{len(amt_str):02d}{amt_str}'

    payload += '5802TH'  # Country Code: TH
    payload += '6304'    # CRC tag & length indicator

    # CRC16-CCITT (Polynomial 0x1021, Initial 0xFFFF)
    crc = 0xFFFF
    for byte in payload.encode('ascii'):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    crc_hex = f'{crc:04X}'
    return payload + crc_hex


def generate_promptpay_qr_base64(target: str, amount: float | Decimal = 1000.00) -> str:
    """
    Generates a branded PNG QR code as a base64 Data URL.
    """
    payload = generate_promptpay_payload(target, amount)
    
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f"data:image/png;base64,{encoded}"


def calculate_file_sha256(file_obj) -> str:
    """
    Computes cryptographic SHA-256 hash of an uploaded file to detect duplicates.
    Rewinds the file pointer back to 0.
    """
    hasher = hashlib.sha256()
    file_obj.seek(0)
    for chunk in file_obj.chunks():
        hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()
