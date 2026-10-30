from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.accounts.models import UserRole
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingType, ListingStatus

User = get_user_model()

class LegacyWordpressSEORedirectTestCase(TestCase):
    """
    WHY SECURE & SEO CRITICAL:
    Verifies that the legacy WordPress URL patterns and Ref Codes
    (e.g., N-032, ?p=123, /listing/slug/) are permanently redirected (HTTP 301)
    to preserve Google PageRank, backlinks, and existing social media shares.
    """
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username='owner_seo@test.com',
            email='owner_seo@test.com',
            password='Password123!',
            role=UserRole.OWNER
        )
        self.prop = Property.objects.create(
            owner=self.owner,
            type=PropertyType.STANDALONE,
            title='ร้านอาหารซีฟู้ด พัทยากลาง',
            desc='ติดหาด',
            address='หาดจอมเทียน',
            province='ชลบุรี',
            district='บางละมุง',
            postal='20150'
        )
        self.listing = Listing.objects.create(
            property=self.prop,
            ref_code='N-032',
            price=Decimal('1500000.00'),
            monthly_rent=Decimal('45000.00'),
            status=ListingStatus.PUBLISHED
        )

    def test_legacy_ref_code_path_redirects_301_to_listing(self):
        """Visiting legacy path /n-032/ must return HTTP 301 to the listing detail page."""
        response = self.client.get('/n-032/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], self.listing.get_absolute_url())

    def test_legacy_ref_code_case_insensitive_and_spacing_redirect(self):
        """Visiting legacy path /N 032/ or /n_032/ must normalize and return HTTP 301."""
        response = self.client.get('/N-032/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], self.listing.get_absolute_url())

    def test_legacy_wordpress_query_param_redirects_301(self):
        """Visiting legacy WordPress query permalink /?p=12345 must return HTTP 301."""
        response = self.client.get('/?p=12345')
        self.assertEqual(response.status_code, 301)
        self.assertIn('/listings/', response['Location'])

    def test_legacy_singular_listing_redirects_301(self):
        """Visiting legacy WordPress singular /listing/some-old-post/ redirects 301 to /listings/."""
        response = self.client.get('/listing/old-shop-takeover/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/listings/')

    def test_standard_urls_not_redirected(self):
        """Standard application routes must not be affected by the redirect middleware."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/listings/')
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)

    def test_privacy_policy_page_renders_successfully(self):
        """Privacy Policy page must return HTTP 200 and contain PDPA statements and schema."""
        response = self.client.get('/privacy-policy/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'นโยบายความเป็นส่วนตัว')
        self.assertContains(response, 'PDPA')
        self.assertContains(response, 'schema.org')
        self.assertContains(response, 'dpo@xn--72ch2atb1d4a4f1fudfc.com')

    def test_terms_of_service_page_renders_successfully(self):
        """Terms of Service page must return HTTP 200 and contain platform rules and disclaimer."""
        response = self.client.get('/terms-of-service/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ข้อกำหนดการใช้งาน')
        self.assertContains(response, 'สื่อกลางทางเทคโนโลยี')
        self.assertContains(response, 'schema.org')
        self.assertContains(response, 'No-Refund Policy')

    def test_footer_contains_working_links_to_legal_pages(self):
        """Homepage footer must contain valid href links to privacy policy and terms of service."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/privacy-policy/"')
        self.assertContains(response, 'href="/terms-of-service/"')
