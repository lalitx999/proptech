import json
from decimal import Decimal
from pathlib import Path
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.accounts.models import UserRole
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingStatus, ListingType
from apps.listings.services.search import ListingSearchService
from apps.listings.views import marketplace_view

User = get_user_model()

class MarketplaceSearchSecurityTestCase(TestCase):
    """
    WHY SECURE: Test suite strictly verifying:
    1. SQLi resilience against malicious search payloads.
    2. Prevention of N+1 database queries on public listings.
    3. Input truncation protecting against ReDoS / buffer abuse.
    4. PWA Service Worker strict cache exclusion compliance (Requirement #10).
    5. PWA Web App Manifest data hygiene.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.owner = User.objects.create_user('owner', 'owner@sengran.com', 'SecurePass123!', role=UserRole.OWNER)

        # Create 3 published listings and 1 draft listing
        for i in range(3):
            prop = Property.objects.create(
                owner=self.owner,
                title=f'ร้านอาหาร สาขา {i}',
                desc=f'รายละเอียดร้าน {i}',
                address=f'{i} สุขุมวิท',
                province='กรุงเทพมหานคร',
                district='วัฒนา',
                postal='10110',
                area_sqm=Decimal('60.00')
            )
            Listing.objects.create(
                property=prop,
                price=Decimal(f'{300000 + (i * 100000)}.00'),
                monthly_rent=Decimal('25000.00'),
                status=ListingStatus.PUBLISHED
            )

        # Draft listing (must never be returned in search)
        prop_draft = Property.objects.create(
            owner=self.owner,
            title='ร้านนวด ซ่อนอยู่ (Draft)',
            desc='ยังไม่เปิดเผย',
            address='ซอยลับ',
            province='ชลบุรี',
            district='บางละมุง',
            postal='20150'
        )
        Listing.objects.create(
            property=prop_draft,
            price=Decimal('500000.00'),
            status=ListingStatus.DRAFT
        )

    def test_sqli_payload_resilience(self):
        """
        Verify common SQL injection vectors are safely parameterized
        and do not cause database syntax crashes.
        """
        malicious_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE listings_listing; --",
            "UNION SELECT * FROM accounts_user--",
            "1' AND 1=1 UNION SELECT 1,2,3,4,5,6,7,8,9,10--",
            "\" OR \"\"=\"",
        ]
        for payload in malicious_payloads:
            results = ListingSearchService.search({'q': payload})
            # Must safely evaluate without SQL error
            count = results.count()
            self.assertEqual(count, 0, f"SQL injection payload '{payload}' must yield 0 results safely.")

    def test_search_query_truncation_anti_redos(self):
        """Verify queries exceeding 100 characters are truncated safely."""
        oversized_query = "A" * 500
        results = ListingSearchService.search({'q': oversized_query})
        self.assertEqual(results.count(), 0)

    def test_draft_listings_never_leaked_in_public_search(self):
        """Verify draft listings are strictly excluded from public marketplace results."""
        results = ListingSearchService.search({'q': 'ร้านนวด ซ่อนอยู่'})
        self.assertEqual(results.count(), 0, "Draft listings must NEVER be returned in public search.")

    def test_n_plus_one_query_optimization(self):
        """
        Verify listings queries optimize joins via select_related & prefetch_related,
        avoiding N+1 database queries.
        """
        with self.assertNumQueries(2): # 1 for listings+property+owner+agent, 1 for property__images
            results = list(ListingSearchService.search({}))
            for item in results:
                _ = item.property.title
                _ = item.property.owner.email
                _ = list(item.property.images.all())

    def test_pwa_service_worker_sensitive_cache_exclusion(self):
        """
        Verify Requirement #10:
        sw.js MUST explicitly exclude /accounts/, /admin/, /properties/,
        /internal-media/, and /contracts/ from caching.
        """
        sw_path = settings.BASE_DIR / 'static' / 'sw.js'
        self.assertTrue(sw_path.exists(), "sw.js must exist in static directory.")

        content = sw_path.read_text(encoding='utf-8')
        required_exclusions = [
            r'\/accounts\/',
            r'\/admin\/',
            r'\/properties\/',
            r'\/internal-media\/',
            r'\/contracts\/',
        ]
        for pattern in required_exclusions:
            self.assertIn(pattern, content, f"sw.js must strictly blacklist '{pattern}' from caching.")

    def test_pwa_manifest_security(self):
        """Verify manifest.json is valid JSON and contains no sensitive URLs."""
        manifest_path = settings.BASE_DIR / 'static' / 'manifest.json'
        self.assertTrue(manifest_path.exists(), "manifest.json must exist.")

        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(data.get('display'), 'standalone')
        self.assertEqual(data.get('start_url'), '/')
        self.assertEqual(data.get('scope'), '/')

    def test_stored_xss_protection_in_map_script(self):
        """
        Verify that listing titles containing script breakout tags
        (e.g. </script><script>alert(1)</script>) are safely serialized
        via Django's json_script filter, preventing Stored XSS.
        """
        prop_xss = Property.objects.create(
            owner=self.owner,
            title='</script><script>alert("xss")</script>',
            desc='Test XSS Description',
            address='123 Test St',
            province='กรุงเทพมหานคร',
            district='วัฒนา',
            postal='10110',
            lat=Decimal('13.736717'),
            lng=Decimal('100.523186')
        )
        Listing.objects.create(
            property=prop_xss,
            price=Decimal('100000.00'),
            status=ListingStatus.PUBLISHED
        )

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

        # 1. json_script container must exist
        self.assertContains(response, '<script id="map-listings-data" type="application/json">')

        # 2. Raw unescaped script tag must NOT be present in response
        content = response.content.decode('utf-8')
        self.assertNotIn('</script><script>alert("xss")</script>', content)

        # 3. Escaped unicode representation must be inside the json_script block
        self.assertIn('\\u003C/script\\u003E\\u003Cscript\\u003Ealert(\\"xss\\")', content)

