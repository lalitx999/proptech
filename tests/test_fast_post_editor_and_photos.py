"""
Admin Fast Post: rich text description, photo ordering, and removed financial fields.

WHY:
1. The Fast Post description is rendered with |safe, so the shared sanitizer must
   strip scripts and must fail closed (never store raw HTML) if bleach errors.
2. Photos are saved in the order the browser submits them; the first is the cover.
3. Average profit/revenue inputs were removed: posted values are ignored and
   editing a listing must not wipe values already stored in the database.
"""
import io
import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import UserRole
from apps.core.utils.html import sanitize_rich_html
from apps.properties.models import Property, PropertyType

User = get_user_model()
MEDIA_ROOT = tempfile.mkdtemp()


def make_image(name, width):
    buf = io.BytesIO()
    Image.new("RGB", (width, 100), color="blue").save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class SanitizeRichHtmlTests(TestCase):
    def test_keeps_formatting_and_strips_scripts(self):
        raw = (
            '<span style="color: #dc2626">ทำเลทอง</span><b>ด่วน</b>'
            '<script>alert(1)</script><img src=x onerror=alert(1)>'
            '<a href="javascript:alert(1)">x</a>'
        )
        clean = sanitize_rich_html(raw)
        self.assertIn('<span style="color: #dc2626;">ทำเลทอง</span>', clean)
        self.assertIn('<b>ด่วน</b>', clean)
        self.assertNotIn('<script', clean)
        self.assertNotIn('onerror', clean)
        self.assertNotIn('javascript:', clean)

    def test_fails_closed_when_bleach_errors(self):
        with patch('apps.core.utils.html.bleach.clean', side_effect=RuntimeError):
            clean = sanitize_rich_html('<b>ok</b><script>alert(1)</script>')
        self.assertNotIn('<', clean)
        self.assertIn('ok', clean)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AdminFastPostTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_user(
            username="fastpost_admin",
            email="fastpost_admin@test.com",
            password="DevPass1234!",
            role=UserRole.ADMIN,
            is_staff=True,
            is_superuser=True,
            email_verified=True,
        )
        self.client.force_login(self.admin)

    def fast_post(self, **extra):
        data = {
            "title": "ร้านทดสอบ Fast Post",
            "category": PropertyType.CAFE_BEVERAGE,
            "province": "ชลบุรี",
            "district": "เมือง",
            "address": "ถนนสุขุมวิท",
            "price": "850000",
            "monthly_rent": "20000",
            "is_published": "1",
        }
        data.update(extra)
        self.client.post(reverse("accounts:admin_fast_create_shop"), data, follow=True)
        return Property.objects.get(title="ร้านทดสอบ Fast Post")

    def test_photos_saved_in_submitted_order_first_is_cover(self):
        prop = self.fast_post(images=[
            make_image("b.jpg", 300),
            make_image("a.jpg", 150),
            make_image("c.jpg", 220),
        ])
        images = list(prop.images.order_by("order"))
        widths = [Image.open(img.image.path).width for img in images]
        self.assertEqual(widths, [300, 150, 220])
        self.assertEqual([img.is_cover for img in images], [True, False, False])

    def test_rich_description_is_sanitized(self):
        prop = self.fast_post(
            description='<span style="color: #16a34a">ใกล้ BTS</span><script>alert(1)</script>'
        )
        self.assertIn('ใกล้ BTS', prop.desc)
        self.assertIn('color: #16a34a', prop.desc)
        self.assertNotIn('<script', prop.desc)

    def test_profit_and_revenue_inputs_are_ignored(self):
        prop = self.fast_post(avg_profit_3m="65000", avg_revenue_3m="220000")
        listing = prop.listings.first()
        self.assertIsNone(listing.avg_profit_3m)
        self.assertIsNone(listing.avg_revenue_3m)

    def test_edit_page_keeps_existing_profit_and_revenue(self):
        prop = self.fast_post()
        listing = prop.listings.first()
        listing.avg_profit_3m = Decimal("60000")
        listing.avg_revenue_3m = Decimal("200000")
        listing.save(update_fields=["avg_profit_3m", "avg_revenue_3m"])

        self.client.post(reverse("properties:property_update", args=[prop.pk]), {
            "title": "ร้านทดสอบ Fast Post",
            "type": PropertyType.CAFE_BEVERAGE,
            "province": "ชลบุรี",
            "district": "เมือง",
            "address": "ถนนสุขุมวิท",
            "desc": "แก้ไขรายละเอียด",
            "price": "800000",
            "monthly_rent": "20000",
        }, follow=True)

        listing.refresh_from_db()
        self.assertEqual(listing.price, Decimal("800000"))
        self.assertEqual(listing.avg_profit_3m, Decimal("60000"))
        self.assertEqual(listing.avg_revenue_3m, Decimal("200000"))

    def test_dashboard_renders_editor_and_photo_picker(self):
        body = self.client.get(reverse("accounts:admin_dashboard") + "?tab=shops").content.decode()
        self.assertIn('id="fast-create-description"', body)
        self.assertIn('data-rte', body)
        self.assertIn('id="fast-create-photos-grid"', body)
        self.assertNotIn('name="avg_profit_3m"', body)
        self.assertNotIn('name="avg_revenue_3m"', body)
