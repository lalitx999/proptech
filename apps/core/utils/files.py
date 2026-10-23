import io
import os
import uuid
import datetime
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image

try:
    import magic
except (ImportError, Exception):
    magic = None

# ==============================================================================
# SECURE UPLOAD PATH GENERATOR
# ==============================================================================
def secure_upload_path(instance, filename, folder='uploads'):
    """
    WHY SECURE:
    1. Prevents Path Traversal attacks (directory traversal like ../../../etc/passwd).
    2. Strips original user filename completely.
    3. Replaces filename with cryptographic UUID4: media/<model>/<yyyy>/<mm>/<uuid>.<ext>
    """
    ext = os.path.splitext(filename)[1].lower()
    now = datetime.datetime.now()
    model_name = instance._meta.model_name if hasattr(instance, '_meta') else folder
    clean_uuid = uuid.uuid4().hex
    return f"{model_name}/{now:%Y}/{now:%m}/{clean_uuid}{ext}"

# ==============================================================================
# FILE VALIDATION & SANITIZATION PIPELINE
# ==============================================================================
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

def check_image_magic_signatures(header_bytes):
    """
    WHY SECURE:
    Direct binary magic signature inspection (Independent of system C-libraries).
    Detects whether file bytes match authentic image standards:
    - JPEG: \\xff\\xd8\\xff
    - PNG:  \\x89PNG\\r\\n\\x1a\\n
    - WEBP: RIFF....WEBP
    """
    if len(header_bytes) < 12:
        return False
    # JPEG
    if header_bytes[:3] == b'\xff\xd8\xff':
        return True
    # PNG
    if header_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    # WEBP
    if header_bytes[:4] == b'RIFF' and header_bytes[8:12] == b'WEBP':
        return True
    return False

def validate_and_sanitize_image(uploaded_file):
    """
    WHY SECURE:
    1. Size Check: Enforces <= 10MB limit (anti-DoS / disk exhaustion).
    2. Extension Check: Whitelist jpg, jpeg, png, webp.
    3. Magic Signature Inspection: Inspects binary headers to block polyglot
       exploits (e.g. PHP scripts or ELF binaries disguised as .jpg).
    4. Pillow Re-encoding: Decodes pixels and re-saves into a clean buffer,
       completely stripping all EXIF metadata (GPS geolocation, device IDs)
       and neutralizing steganographic payload injection.
    """
    # 1. File size check
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError("ขนาดรูปภาพต้องไม่เกิน 10 MB")

    # 2. Extension whitelist check
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"นามสกุลไฟล์ไม่ถูกต้อง อนุญาตเฉพาะ {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")

    # 3. Magic bytes inspection
    uploaded_file.seek(0)
    file_header = uploaded_file.read(2048)
    uploaded_file.seek(0)

    if not check_image_magic_signatures(file_header):
        raise ValidationError("เนื้อหาไฟล์ไม่ตรงกับรูปภาพจริง (ตรวจพบ Magic Bytes ไม่ถูกต้อง)")

    if magic:
        try:
            mime_type = magic.from_buffer(file_header, mime=True)
            if mime_type not in ALLOWED_IMAGE_MIMES:
                raise ValidationError(f"เนื้อหาไฟล์ไม่ตรงกับรูปภาพจริง (ตรวจพบ MIME: {mime_type})")
        except Exception:
            pass

    # 4. Pillow verification & EXIF sanitization
    try:
        with Image.open(uploaded_file) as img:
            img.verify()
    except Exception:
        raise ValidationError("ไฟล์รูปภาพเสียหายหรือไม่ถูกต้อง")

    # Re-open for clean re-encoding and stripping EXIF
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        img_format = img.format if img.format in ['JPEG', 'PNG', 'WEBP'] else 'JPEG'
        output_buffer = io.BytesIO()

        if img_format == 'JPEG' and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Re-save without original info/exif dictionaries
        img.save(output_buffer, format=img_format, quality=85, optimize=True)
        output_buffer.seek(0)

        return InMemoryUploadedFile(
            file=output_buffer,
            field_name=uploaded_file.field_name if hasattr(uploaded_file, 'field_name') else None,
            name=f"{uuid.uuid4().hex}{ext}",
            content_type=f"image/{img_format.lower()}",
            size=output_buffer.getbuffer().nbytes,
            charset=None
        )
