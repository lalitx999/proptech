import io
from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.accounts.models import UserRole, VIPPaymentTransaction
from apps.accounts.services.promptpay import (
    generate_promptpay_payload,
    generate_promptpay_qr_base64,
    calculate_file_sha256,
)
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingStatus

User = get_user_model()

def create_test_image(filename="test.jpg", color="blue"):
    file_obj = io.BytesIO()
    image = Image.new("RGB", (100, 100), color=color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(filename, file_obj.read(), content_type="image/jpeg")


class VIPMembershipAndQuotaTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="shopowner",
            email="owner@example.com",
            password="SecurePassword123!",
            role=UserRole.OWNER,
            is_active=True,
            email_verified=True,
        )
        self.staff_user = User.objects.create_user(
            username="staffadmin",
            email="staff@example.com",
            password="SecurePassword123!",
            role=UserRole.STAFF,
            is_active=True,
            email_verified=True,
        )

    def test_unauthenticated_user_can_view_vip_and_packages_page(self):
        """Unauthenticated guests can view VIP membership and packages page without login."""
        url = reverse("accounts:vip_membership")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "โพสต์ VIP")
        self.assertContains(response, "Super VIP")
        self.assertContains(response, "ผู้เข้าชมทั่วไป")

        # Core package alias
        packages_url = reverse("core:packages")
        res_pkg = self.client.get(packages_url)
        self.assertEqual(res_pkg.status_code, 200)

    def test_unauthenticated_user_post_slip_redirects_to_login(self):
        """Unauthenticated guests attempting to submit a payment slip are redirected to login."""
        url = reverse("accounts:vip_membership")
        slip_image = create_test_image("guest_slip.jpg", "blue")
        response = self.client.post(url, {"slip_image": slip_image})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_free_member_quota(self):
        """Free members get 1 post per calendar month."""
        self.assertFalse(self.owner.is_vip_active)
        self.assertEqual(self.owner.get_monthly_quota(), 1)
        self.assertEqual(self.owner.get_remaining_quota(), 1)
        self.assertTrue(self.owner.can_post_listing())

        # Create 1 property in current month
        Property.objects.create(
            owner=self.owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Cafe 1",
            desc="Desc",
            address="123 Road",
            province="กรุงเทพฯ",
            district="วัฒนา",
            postal="10110",
        )

        self.assertEqual(self.owner.get_current_month_posts_count(), 1)
        self.assertEqual(self.owner.get_remaining_quota(), 0)
        self.assertFalse(self.owner.can_post_listing())

    def test_vip_member_quota(self):
        """VIP members get 4 posts per calendar month."""
        self.owner.is_vip = True
        self.owner.vip_expires_at = timezone.now() + datetime.timedelta(days=30)
        self.owner.save()

        self.assertTrue(self.owner.is_vip_active)
        self.assertEqual(self.owner.get_monthly_quota(), 4)
        self.assertEqual(self.owner.get_remaining_quota(), 4)
        self.assertTrue(self.owner.can_post_listing())

        # Create 3 properties
        for i in range(3):
            Property.objects.create(
                owner=self.owner,
                type=PropertyType.CAFE_BEVERAGE,
                title=f"Shop {i}",
                desc="Desc",
                address="Address",
                province="กรุงเทพฯ",
                district="วัฒนา",
                postal="10110",
            )

        self.assertEqual(self.owner.get_current_month_posts_count(), 3)
        self.assertEqual(self.owner.get_remaining_quota(), 1)
        self.assertTrue(self.owner.can_post_listing())

        # Post 4th
        Property.objects.create(
            owner=self.owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Shop 4",
            desc="Desc",
            address="Address",
            province="กรุงเทพฯ",
            district="วัฒนา",
            postal="10110",
        )
        self.assertEqual(self.owner.get_remaining_quota(), 0)
        self.assertFalse(self.owner.can_post_listing())

    def test_promptpay_payload_generation(self):
        """PromptPay EMVCo payload format and amount locking."""
        payload = generate_promptpay_payload("0812345678", 1000.00)
        self.assertTrue(payload.startswith("000201"))
        self.assertIn("54071000.00", payload)  # Locked amount 1000.00
        self.assertIn("5303764", payload)      # Currency THB
        self.assertIn("5802TH", payload)       # Thailand country code

        qr_base64 = generate_promptpay_qr_base64("0812345678", 1000.00)
        self.assertTrue(qr_base64.startswith("data:image/png;base64,"))

    def test_vip_slip_upload_and_sha256_duplicate_detection(self):
        """Uploading a duplicate slip must be rejected by SHA-256 check."""
        self.client.force_login(self.owner)
        url = reverse("accounts:vip_membership")

        slip_image = create_test_image("slip1.jpg", "green")

        # 1st upload succeeds
        response = self.client.post(url, {"slip_image": slip_image}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(VIPPaymentTransaction.objects.filter(user=self.owner).count(), 1)
        tx = VIPPaymentTransaction.objects.first()
        self.assertEqual(tx.amount, Decimal("1000.00"))
        self.assertEqual(tx.status, VIPPaymentTransaction.Status.PENDING)
        self.assertTrue(len(tx.slip_hash) == 64)

        # 2nd upload with identical slip image must be rejected
        slip_image_dup = create_test_image("slip1.jpg", "green")
        response_dup = self.client.post(url, {"slip_image": slip_image_dup}, follow=True)
        self.assertContains(response_dup, "สลิปนี้เคยถูกส่งเข้าระบบแล้ว")
        self.assertEqual(VIPPaymentTransaction.objects.count(), 1)

    def test_staff_approve_vip_transaction(self):
        """Staff approves pending transaction and grants 30 days of VIP."""
        # Create a pending transaction
        slip_img = create_test_image("slip_test.jpg", "red")
        import hashlib
        tx = VIPPaymentTransaction.objects.create(
            user=self.owner,
            ref_number="VIP-TEST-001",
            amount=Decimal("1000.00"),
            slip_image=slip_img,
            slip_hash=hashlib.sha256(b"dummy_test_slip").hexdigest(),
            status=VIPPaymentTransaction.Status.PENDING,
        )

        self.client.force_login(self.staff_user)
        approve_url = reverse("accounts:vip_approve", kwargs={"pk": tx.pk})
        response = self.client.post(approve_url, {"action": "approve"}, follow=True)
        self.assertEqual(response.status_code, 200)

        tx.refresh_from_db()
        self.assertEqual(tx.status, VIPPaymentTransaction.Status.MANUAL_APPROVED)
        self.assertEqual(tx.reviewed_by, self.staff_user)

        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_vip)
        self.assertTrue(self.owner.is_vip_active)
        self.assertGreater(self.owner.vip_expires_at, timezone.now())


class ConsignmentWizardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="wizarduser",
            email="wizard@example.com",
            password="SecurePassword123!",
            role=UserRole.OWNER,
            is_active=True,
            email_verified=True,
        )

    def test_consignment_wizard_page_get(self):
        """Wizard page loads properly for authenticated user."""
        self.client.force_login(self.owner)
        url = reverse("listings:listing_create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ลงประกาศเซ้งร้าน")
        self.assertContains(response, "1. ข้อมูลร้าน & ทำเล")

    def test_consignment_wizard_post_success(self):
        """Wizard multi-step submission creates Property, PropertyImage, and Listing."""
        self.client.force_login(self.owner)
        url = reverse("listings:listing_create")

        image1 = create_test_image("store1.jpg", "purple")
        image2 = create_test_image("store2.jpg", "orange")

        post_data = {
            "title": "เซ้งร้านชานมไข่มุก สยามสแควร์ แหล่งวัยรุ่น",
            "property_type": PropertyType.CAFE_BEVERAGE,
            "province": "กรุงเทพมหานคร",
            "district": "ปทุมวัน",
            "postal": "10330",
            "address": "สยามสแควร์ ซอย 3",
            "price": "450000",
            "monthly_rent": "35000",
            "security_deposit": "70000",
            "lease_remaining_months": "24",
            "lease_transfer_fee": "0",
            "lease_transfer_fee_payer": "free",
            "avg_revenue_3m": "180000",
            "avg_profit_3m": "65000",
            "area_sqm": "32",
            "floors": "1",
            "desc": "ทำเลทองใจกลางสยาม พร้อมสูตรและเครื่องต้มชา La Marzocco",
            "includes_equipment": "ตู้เย็น, เคาน์เตอร์, เครื่องซีลฝาแก้ว",
            "includes_staff": "true",
            "images": [image1, image2],
        }

        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Check DB
        prop = Property.objects.filter(owner=self.owner).first()
        self.assertIsNotNone(prop)
        self.assertEqual(prop.title, "เซ้งร้านชานมไข่มุก สยามสแควร์ แหล่งวัยรุ่น")
        self.assertEqual(prop.images.count(), 2)

        listing = Listing.objects.filter(property=prop).first()
        self.assertIsNotNone(listing)
        self.assertEqual(listing.price, Decimal("450000"))
        self.assertEqual(listing.status, ListingStatus.PUBLISHED)
        self.assertTrue(listing.includes_staff)

    def test_consignment_post_quota_exceeded(self):
        """User cannot submit when monthly quota is exhausted."""
        self.client.force_login(self.owner)
        url = reverse("listings:listing_create")

        # Create 1 listing already for current month
        Property.objects.create(
            owner=self.owner,
            type=PropertyType.RETAIL_SHOP,
            title="First Shop",
            desc="Desc",
            address="Address",
            province="กรุงเทพฯ",
            district="บางรัก",
            postal="10500",
        )

        # Try to post second shop
        image = create_test_image("store3.jpg", "yellow")
        post_data = {
            "title": "เซ้งร้านที่สอง ไม่ควรผ่าน",
            "property_type": PropertyType.RETAIL_SHOP,
            "province": "กรุงเทพฯ",
            "district": "บางรัก",
            "postal": "10500",
            "address": "สีลม",
            "price": "300000",
            "images": [image],
        }

        response = self.client.post(url, post_data, follow=False)
        # Should redirect to VIP membership upgrade
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:vip_membership"), response.url)

    def test_compare_listings_view(self):
        """Compare view renders comparison matrix for requested listing IDs."""
        p1 = Property.objects.create(
            owner=self.owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Cafe Comparison 1",
            desc="Desc",
            address="Addr 1",
            province="กรุงเทพฯ",
            district="ปทุมวัน",
            postal="10330",
        )
        l1 = Listing.objects.create(
            property=p1,
            price=Decimal("300000"),
            monthly_rent=Decimal("20000"),
            status=ListingStatus.PUBLISHED,
        )

        p2 = Property.objects.create(
            owner=self.owner,
            type=PropertyType.RESTAURANT_SHABU,
            title="Restaurant Comparison 2",
            desc="Desc",
            address="Addr 2",
            province="ชลบุรี",
            district="บางละมุง",
            postal="20150",
        )
        l2 = Listing.objects.create(
            property=p2,
            price=Decimal("500000"),
            monthly_rent=Decimal("35000"),
            status=ListingStatus.PUBLISHED,
        )

        url = f"{reverse('listings:listing_compare')}?ids={l1.id},{l2.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cafe Comparison 1")
        self.assertContains(response, "Restaurant Comparison 2")
        self.assertContains(response, "300,000")
        self.assertContains(response, "500,000")

    def test_favorites_view(self):
        """Favorites view renders saved listings."""
        p = Property.objects.create(
            owner=self.owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Favorite Cafe 1",
            desc="Desc",
            address="Addr",
            province="เชียงใหม่",
            district="เมือง",
            postal="50200",
        )
        l = Listing.objects.create(
            property=p,
            price=Decimal("250000"),
            status=ListingStatus.PUBLISHED,
        )

        url = f"{reverse('listings:listing_favorites')}?ids={l.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Favorite Cafe 1")
        self.assertContains(response, "250,000")


class ListingRefCodeGenerationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.free_owner = User.objects.create_user(
            username="freeuser",
            email="free@example.com",
            password="Password123!",
            role=UserRole.OWNER,
            is_vip=False,
        )
        self.vip_owner = User.objects.create_user(
            username="vipuser",
            email="vip@example.com",
            password="Password123!",
            role=UserRole.OWNER,
            is_vip=True,
            vip_expires_at=timezone.now() + datetime.timedelta(days=30),
        )
        self.admin = User.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="Password123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

    def test_free_listings_sequential_f_codes(self):
        """Free listings auto-generate sequential F001, F002..."""
        p1 = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Free Shop 1",
            district="ปทุมวัน",
            province="กรุงเทพมหานคร",
        )
        l1 = Listing.objects.create(property=p1, price=Decimal("100000"))
        self.assertEqual(l1.ref_code, "F001")

        p2 = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.RESTAURANT_SHABU,
            title="Free Shop 2",
            district="บางรัก",
            province="กรุงเทพมหานคร",
        )
        l2 = Listing.objects.create(property=p2, price=Decimal("200000"))
        self.assertEqual(l2.ref_code, "F002")

    def test_vip_listings_sequential_v_codes(self):
        """VIP listings (1,000 THB) auto-generate sequential V001, V002..."""
        p1 = Property.objects.create(
            owner=self.vip_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="VIP Shop 1",
            district="วัฒนา",
            province="กรุงเทพมหานคร",
        )
        l1 = Listing.objects.create(property=p1, price=Decimal("350000"))
        self.assertEqual(l1.ref_code, "V001")

        p2 = Property.objects.create(
            owner=self.vip_owner,
            type=PropertyType.RESTAURANT_SHABU,
            title="VIP Shop 2",
            district="คลองเตย",
            province="กรุงเทพมหานคร",
        )
        l2 = Listing.objects.create(property=p2, price=Decimal("500000"))
        self.assertEqual(l2.ref_code, "V002")

    def test_admin_manual_n_and_s_codes(self):
        """Admin can assign custom ref codes such as N001 (agent) or S001 (super vip)"""
        p_agent = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.RETAIL_SHOP,
            title="Broker Managed Shop",
            district="สาทร",
            province="กรุงเทพมหานคร",
        )
        l_agent = Listing.objects.create(
            property=p_agent,
            ref_code="N001",
            price=Decimal("800000"),
        )
        self.assertEqual(l_agent.ref_code, "N001")

        p_super = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.RETAIL_SHOP,
            title="Super VIP Shop",
            district="ทองหล่อ",
            province="กรุงเทพมหานคร",
        )
        l_super = Listing.objects.create(
            property=p_super,
            ref_code="S001",
            price=Decimal("1200000"),
        )
        self.assertEqual(l_super.ref_code, "S001")

    def test_admin_edit_ref_code_action(self):
        """Admin can edit listing ref_code via shop action with duplicate protection"""
        self.client.force_login(self.admin)
        p = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Editable Ref Shop",
            district="พญาไท",
            province="กรุงเทพมหานคร",
        )
        l = Listing.objects.create(property=p, price=Decimal("150000"))
        self.assertEqual(l.ref_code, "F001")

        # Edit to N001
        url = reverse("accounts:admin_shop_action", kwargs={"pk": l.pk})
        resp = self.client.post(url, {"action": "edit_ref_code", "ref_code": "N001"})
        self.assertEqual(resp.status_code, 302)
        l.refresh_from_db()
        self.assertEqual(l.ref_code, "N001")

        # Test duplicate code rejection
        p2 = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.RETAIL_SHOP,
            title="Another Shop",
            district="จตุจักร",
            province="กรุงเทพมหานคร",
        )
        l2 = Listing.objects.create(property=p2, price=Decimal("300000"))
        resp_dup = self.client.post(
            reverse("accounts:admin_shop_action", kwargs={"pk": l2.pk}),
            {"action": "edit_ref_code", "ref_code": "N001"},
        )
        self.assertEqual(resp_dup.status_code, 302)
        l2.refresh_from_db()
        self.assertNotEqual(l2.ref_code, "N001")

    def test_free_quota_enforced_on_property_create(self):
        """Free user who used their monthly quota is blocked and redirected to VIP membership"""
        self.client.force_login(self.free_owner)
        # Create 1 listing which uses the 1 monthly quota
        p1 = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="First Free Shop",
            district="พระโขนง",
            province="กรุงเทพมหานคร",
        )
        Listing.objects.create(property=p1, price=Decimal("120000"))
        self.assertFalse(self.free_owner.can_post_listing())

        # Attempt to access property create view
        url = reverse("properties:property_create")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:vip_membership"), resp.url)

    def test_contact_form_saves_line_id(self):
        """Contact form saves line_id in ContactMessage"""
        from apps.core.models import ContactMessage
        url = reverse("core:contact")
        post_data = {
            "name": "สมชาย คนดี",
            "phone": "0812345678",
            "line_id": "somchai_line_id",
            "subject": "สนใจลงประกาศเซ้งร้าน",
            "message": "ต้องการสอบถามรายละเอียดเพิ่มเติมครับ",
        }
        resp = self.client.post(url, post_data)
        self.assertEqual(resp.status_code, 302)
        msg = ContactMessage.objects.filter(phone="0812345678").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.line_id, "somchai_line_id")

    def test_telegram_new_listing_and_vip_real_amount(self):
        """Telegram alert handles real slip amount and new listing alert"""
        from apps.core.services.telegram import TelegramAlertService
        from apps.accounts.models import VIPPaymentTransaction, MembershipTier

        # 1. VIP Alert with real 1.00 THB amount
        tx = VIPPaymentTransaction.objects.create(
            user=self.free_owner,
            ref_number="VIP-TEST-001",
            tier=MembershipTier.VIP,
            amount=Decimal("1.00"),
            status=VIPPaymentTransaction.Status.PENDING,
        )
        # Mock mode returns False or True without crash
        alert_sent = TelegramAlertService.send_vip_alert(tx, auto_verified=False)
        self.assertIn(alert_sent, [True, False])

        # 2. New Listing Alert
        p = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Cafe Telegram Test",
            district="ดินแดง",
            province="กรุงเทพมหานคร",
        )
        listing = Listing.objects.create(
            property=p,
            price=Decimal("200000"),
            contact_phone="0899998888",
            contact_line_id="cafe_line",
        )
        listing_alert_sent = TelegramAlertService.send_new_listing_alert(listing)
        self.assertIn(listing_alert_sent, [True, False])

    def test_listing_detail_facebook_share_button(self):
        """Listing detail page renders Facebook share button and owner contact info"""
        p = Property.objects.create(
            owner=self.free_owner,
            type=PropertyType.CAFE_BEVERAGE,
            title="Shareable Cafe",
            district="พญาไท",
            province="กรุงเทพมหานคร",
        )
        listing = Listing.objects.create(
            property=p,
            price=Decimal("450000"),
            contact_phone="0812344321",
            contact_line_id="shareable_line",
            status=ListingStatus.PUBLISHED,
        )
        url = reverse("listings:listing_detail", kwargs={"pk": listing.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "facebook.com/sharer/sharer.php")
        self.assertContains(resp, "0812344321")
        self.assertContains(resp, "shareable_line")


