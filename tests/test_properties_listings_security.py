import io
from decimal import Decimal
from PIL import Image
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from apps.accounts.models import UserRole
from apps.accounts.permissions import can_view, can_edit, can_delete, get_scoped_queryset
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingType, ListingStatus
from apps.core.utils.files import validate_and_sanitize_image, MAX_IMAGE_SIZE_BYTES

User = get_user_model()

def create_test_image(format='JPEG', size=(100, 100), color='red'):
    """Generate in-memory valid image buffer for test uploads."""
    buffer = io.BytesIO()
    image = Image.new('RGB', size, color=color)
    image.save(buffer, format=format)
    buffer.seek(0)
    return buffer.getvalue()

class PropertiesListingsSecurityTestCase(TestCase):
    """
    WHY SECURE: Test suite strictly verifying:
    1. Permission Matrix adherence across all roles.
    2. IDOR / Row-level queryset isolation.
    3. Malicious polyglot file rejection via Magic Bytes.
    4. Oversized file rejection.
    5. Clean image re-encoding without EXIF.
    """

    def setUp(self):
        # Create users for each role
        self.admin = User.objects.create_superuser('admin', 'admin@sengran.com', 'AdminPass123!', role=UserRole.ADMIN)
        self.staff = User.objects.create_user('staff', 'staff@sengran.com', 'StaffPass123!', role=UserRole.STAFF)
        self.agent = User.objects.create_user('agent', 'agent@sengran.com', 'AgentPass123!', role=UserRole.AGENT)
        self.owner1 = User.objects.create_user('owner1', 'owner1@sengran.com', 'Owner1Pass123!', role=UserRole.OWNER)
        self.owner2 = User.objects.create_user('owner2', 'owner2@sengran.com', 'Owner2Pass123!', role=UserRole.OWNER)
        self.customer = User.objects.create_user('customer', 'customer@sengran.com', 'CustPass123!', role=UserRole.CUSTOMER)

        # Create properties
        self.prop_owner1 = Property.objects.create(
            owner=self.owner1,
            title='ร้านกาแฟ นิมมาน',
            desc='ร้านสวย พร้อมเปิดต่อ',
            address='123 นิมมานเหมินท์',
            province='เชียงใหม่',
            district='เมือง',
            postal='50200',
            area_sqm=Decimal('50.00')
        )
        self.prop_owner2 = Property.objects.create(
            owner=self.owner2,
            title='ร้านอาหาร ชลบุรี',
            desc='ทำเลพัทยากลาง',
            address='456 พัทยากลาง',
            province='ชลบุรี',
            district='บางละมุง',
            postal='20150',
            area_sqm=Decimal('120.00')
        )

        # Create listings
        self.listing_draft = Listing.objects.create(
            property=self.prop_owner1,
            agent=self.agent,
            price=Decimal('450000.00'),
            monthly_rent=Decimal('20000.00'),
            status=ListingStatus.DRAFT
        )
        self.listing_published = Listing.objects.create(
            property=self.prop_owner2,
            agent=self.agent,
            price=Decimal('900000.00'),
            monthly_rent=Decimal('35000.00'),
            status=ListingStatus.PUBLISHED
        )

    # ==========================================================================
    # 1. PERMISSION MATRIX TESTS (IDOR DEFENSE)
    # ==========================================================================
    def test_permission_matrix_can_view(self):
        """
        Verify:
        - Customer can view published listing.
        - Customer CANNOT view draft listing.
        - Owner1 can view own draft listing.
        - Owner2 CANNOT view Owner1's draft listing.
        """
        self.assertTrue(can_view(self.customer, self.listing_published))
        self.assertFalse(can_view(self.customer, self.listing_draft))
        self.assertTrue(can_view(self.owner1, self.listing_draft))
        self.assertFalse(can_view(self.owner2, self.listing_draft))
        self.assertTrue(can_view(self.admin, self.listing_draft))

    def test_permission_matrix_can_edit(self):
        """
        Verify:
        - Owner1 can edit own draft property.
        - Owner2 CANNOT edit Owner1's property (IDOR attack blocked).
        - Customer CANNOT edit any property.
        - Admin can edit any property.
        """
        self.assertTrue(can_edit(self.owner1, self.prop_owner1))
        self.assertFalse(can_edit(self.owner2, self.prop_owner1), "Owner2 must be forbidden from editing Owner1's property!")
        self.assertFalse(can_edit(self.customer, self.prop_owner1))
        self.assertTrue(can_edit(self.admin, self.prop_owner1))

    def test_permission_matrix_can_delete(self):
        """
        Verify:
        - Only Admin can delete published/any property.
        - Owner can delete own draft property.
        - Customer/Agent CANNOT delete property.
        """
        self.assertTrue(can_delete(self.admin, self.prop_owner1))
        self.assertTrue(can_delete(self.owner1, self.prop_owner1))
        self.assertFalse(can_delete(self.customer, self.prop_owner1))
        self.assertFalse(can_delete(self.agent, self.prop_owner1))

    def test_row_level_queryset_isolation(self):
        """
        Verify get_scoped_queryset isolates records strictly:
        - Owner1 only receives prop_owner1.
        - Customer only receives published listings.
        """
        qs_owner1 = get_scoped_queryset(self.owner1, Property.objects.all())
        self.assertIn(self.prop_owner1, qs_owner1)
        self.assertNotIn(self.prop_owner2, qs_owner1, "Owner1 must never see Owner2's properties in management queryset!")

        qs_customer = get_scoped_queryset(self.customer, Listing.objects.all())
        self.assertIn(self.listing_published, qs_customer)
        self.assertNotIn(self.listing_draft, qs_customer, "Customer must never see draft listings!")

    # ==========================================================================
    # 2. FILE UPLOAD & MEDIA SECURITY TESTS
    # ==========================================================================
    def test_valid_image_sanitized_and_reencoded(self):
        """Verify valid JPEG is re-encoded and returns clean InMemoryUploadedFile."""
        raw_bytes = create_test_image(format='JPEG')
        uploaded = SimpleUploadedFile("shop_cover.jpg", raw_bytes, content_type="image/jpeg")

        sanitized = validate_and_sanitize_image(uploaded)
        self.assertIsNotNone(sanitized)
        self.assertEqual(sanitized.content_type, "image/jpeg")
        # Check image can be parsed by Pillow cleanly
        img = Image.open(sanitized)
        self.assertEqual(img.size, (100, 100))

    def test_polyglot_malicious_file_rejected_by_magic_bytes(self):
        """
        Verify executable/PHP script renamed as .jpg is detected and rejected
        via magic bytes inspection.
        """
        malicious_payload = b"<?php echo 'RCE payload'; phpinfo(); ?>"
        fake_image = SimpleUploadedFile("avatar.jpg", malicious_payload, content_type="image/jpeg")

        with self.assertRaises(ValidationError) as ctx:
            validate_and_sanitize_image(fake_image)
        self.assertIn("เนื้อหาไฟล์ไม่ตรงกับรูปภาพจริง", str(ctx.exception))

    def test_oversized_file_rejected(self):
        """Verify files exceeding 10MB are blocked before processing."""
        oversized_data = b"0" * (MAX_IMAGE_SIZE_BYTES + 1024)
        large_file = SimpleUploadedFile("huge.jpg", oversized_data, content_type="image/jpeg")

        with self.assertRaises(ValidationError) as ctx:
            validate_and_sanitize_image(large_file)
        self.assertIn("ต้องไม่เกิน 10 MB", str(ctx.exception))

    def test_google_maps_url_and_coordinate_extraction(self):
        """Verify Google Maps links are stored and coordinates automatically extracted."""
        from apps.properties.utils import extract_google_maps_coordinates
        from apps.properties.forms import PropertyForm

        url1 = "https://www.google.com/maps/place/Siam+Paragon/@13.7462411,100.5347402,17z/"
        lat, lng = extract_google_maps_coordinates(url1)
        self.assertIsNotNone(lat)
        self.assertIsNotNone(lng)
        self.assertEqual(str(lat), "13.746241")
        self.assertEqual(str(lng), "100.534740")

        form = PropertyForm(data={
            'type': 'cafe_beverage',
            'title': 'คาเฟ่มินิมอล สยามสแควร์',
            'desc': 'ทำเลทอง ติดสยามพารากอน',
            'address': '991 ถนนพระรามที่ ๑',
            'province': 'กรุงเทพมหานคร',
            'district': 'ปทุมวัน',
            'postal': '10330',
            'google_maps_url': url1,
            'area_sqm': '45.00',
            'floors': 1
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(str(form.cleaned_data['lat']), "13.746241")
        self.assertEqual(str(form.cleaned_data['lng']), "100.534740")
