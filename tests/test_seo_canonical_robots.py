"""
SEO / AEO regression suite — canonical tags, index control, sitemap & structured data.

WHY THESE TESTS EXIST
---------------------
Every rule here maps to a failure mode that silently destroys organic traffic:

1. A wrong/missing <link rel="canonical"> splits ranking signals across duplicate URLs.
2. A private page that is indexable leaks customer data into Google's index.
3. A filtered search URL (?q=...) indexed at scale is the classic "faceted navigation"
   penalty — thousands of near-duplicate thin pages.
4. A sitemap that contains draft listings or omits <lastmod> wastes crawl budget.
5. robots.txt that blocks the commercial VIP landing page de-indexes a revenue page.
6. Hardcoded schema.org values (availability / priceValidUntil) turn into false
   advertising once a shop is sold.
"""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import json
import re
import struct
import xml.etree.ElementTree as ET

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import UserRole
from apps.listings.models import Listing, ListingStatus, ListingType
from apps.properties.models import Property, PropertyType

User = get_user_model()

SITE_URL = settings.SITE_URL.rstrip('/')

CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]+)"')


def png_dimensions(path: Path):
    """Read width/height straight from the PNG IHDR chunk (no Pillow dependency)."""
    with path.open('rb') as handle:
        header = handle.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG file'
    return struct.unpack('>II', header[16:24])


def canonical_of(response):
    match = CANONICAL_RE.search(response.content.decode('utf-8'))
    return match.group(1) if match else None


def robots_of(response):
    match = ROBOTS_RE.search(response.content.decode('utf-8'))
    return match.group(1) if match else None


class SeoFixtureMixin:
    """Shared owner -> property -> listing graph used across the SEO assertions."""

    def create_listing(self, ref_code, status=ListingStatus.PUBLISHED, title=None):
        prop = Property.objects.create(
            owner=self.owner,
            type=PropertyType.STANDALONE,
            title=title or f'ร้านกาแฟทำเลทอง {ref_code}',
            desc='ติดถนนใหญ่ ใกล้ BTS',
            address='สุขุมวิท 55',
            province='กรุงเทพมหานคร',
            district='วัฒนา',
            postal='10110',
        )
        return Listing.objects.create(
            property=prop,
            ref_code=ref_code,
            type=ListingType.TAKEOVER,
            price=Decimal('1500000.00'),
            monthly_rent=Decimal('35000.00'),
            status=status,
        )

    def owner_factory(self, username):
        self.owner = User.objects.create_user(
            username=username,
            email=username,
            password='Password123!',
            role=UserRole.OWNER,
        )
        return self.owner


class CanonicalTagTestCase(SeoFixtureMixin, TestCase):
    """One document = one canonical URL, for every public page type."""

    def setUp(self):
        self.client = Client()
        self.owner_factory('owner_canon@test.com')
        self.listing = self.create_listing('N-777')

    def test_home_canonical_is_site_root(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(canonical_of(response), f'{SITE_URL}/')
        self.assertIn('index', robots_of(response))

    def test_static_pages_have_self_referencing_canonical(self):
        for path in ('/about/', '/contact/', '/accounts/vip/', '/listings/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(canonical_of(response), f'{SITE_URL}{path}')

    def test_listing_detail_canonical_ignores_tracking_query_string(self):
        url = self.listing.get_absolute_url()
        response = self.client.get(f'{url}?utm_source=facebook&utm_campaign=x')
        self.assertEqual(response.status_code, 200)
        # Canonical must be the clean URL, never the tracked variant.
        self.assertEqual(canonical_of(response), f'{SITE_URL}{url}')

    def test_hreflang_point_at_the_same_canonical_url(self):
        response = self.client.get('/about/')
        body = response.content.decode('utf-8')
        self.assertIn(f'<link rel="alternate" hreflang="th-TH" href="{SITE_URL}/about/">', body)
        self.assertIn(f'<link rel="alternate" hreflang="x-default" href="{SITE_URL}/about/">', body)

    def test_listing_detail_exposes_og_metadata(self):
        url = self.listing.get_absolute_url()
        body = self.client.get(url).content.decode('utf-8')
        self.assertIn(f'<meta property="og:url" content="{SITE_URL}{url}">', body)
        self.assertIn('og:image:width', body)
        self.assertIn('og:image:height', body)

    def test_templates_do_not_hardcode_production_host(self):
        """
        WHY: A hardcoded https://www.xn--72ch2atb1d4a4f1fudfc.com in JSON-LD survives staging/preview
        deployments and emits structured data pointing at the wrong host.
        """
        templates_dir = Path(settings.BASE_DIR) / 'templates'
        offenders = [
            str(path.relative_to(templates_dir))
            for path in templates_dir.rglob('*.html')
            if 'https://www.xn--72ch2atb1d4a4f1fudfc.com' in path.read_text(encoding='utf-8')
        ]
        self.assertEqual(offenders, [], f'Hardcoded production domain in: {offenders}')


class FacetedSearchIndexControlTestCase(SeoFixtureMixin, TestCase):
    """Filtered marketplace URLs must be crawlable but NOT indexable."""

    def setUp(self):
        self.client = Client()
        self.owner_factory('owner_facet@test.com')
        self.create_listing('N-801')

    def test_unfiltered_marketplace_is_indexable_and_self_canonical(self):
        response = self.client.get('/listings/')
        self.assertEqual(canonical_of(response), f'{SITE_URL}/listings/')
        self.assertIn('index', robots_of(response))

    def test_filtered_marketplace_is_noindex_and_canonicalised(self):
        for query in ('?q=กาแฟ', '?province=กรุงเทพมหานคร', '?price_max=500000', '?type=takeover'):
            with self.subTest(query=query):
                response = self.client.get(f'/listings/{query}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(robots_of(response), 'noindex, follow')
                # Canonical folds the facet back into the single indexable document.
                self.assertEqual(canonical_of(response), f'{SITE_URL}/listings/')

    def test_page_two_is_indexable_with_self_referencing_canonical(self):
        for index in range(2, 15):
            self.create_listing(f'N-9{index:02d}')
        response = self.client.get('/listings/?page=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(canonical_of(response), f'{SITE_URL}/listings/?page=2')
        self.assertIn('index', robots_of(response))

    def test_sorted_marketplace_stays_indexable(self):
        """Sorting alone is not a facet: the document is still the canonical listing index."""
        response = self.client.get('/listings/?sort=price_asc')
        self.assertIn('index', robots_of(response))


class PrivatePageIndexControlTestCase(TestCase):
    """X-Robots-Tag must be attached at the response layer for non-public surfaces."""

    def setUp(self):
        self.client = Client()

    def test_private_prefixes_send_noindex_header(self):
        for path in ('/accounts/login/', '/accounts/register/', '/properties/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(
                    response.get('X-Robots-Tag'), 'noindex, nofollow',
                    f'{path} must never be indexable (got {response.get("X-Robots-Tag")!r})',
                )

    def test_vip_landing_page_is_explicitly_allowed(self):
        """The VIP page lives under /accounts/ but is a commercial landing page."""
        response = self.client.get('/accounts/vip/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get('X-Robots-Tag'))
        self.assertIn('index', robots_of(response))

    def test_404_page_is_noindex(self):
        response = self.client.get('/no-such-page-exists-here/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_non_html_responses_untouched(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get('X-Robots-Tag'))


class RobotsTxtTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def response_body(self):
        return self.client.get('/robots.txt').content.decode('utf-8')

    def test_robots_txt_served_as_plain_text(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_vip_page_allow_beats_accounts_disallow(self):
        """
        RFC 9309: the LONGEST matching rule wins, so `Allow: /accounts/vip/`
        overrides `Disallow: /accounts/`. Without it the revenue page is blocked.
        """
        body = self.response_body()
        self.assertIn('Allow: /accounts/vip/', body)
        self.assertIn('Disallow: /accounts/', body)

    def test_structured_data_files_are_whitelisted(self):
        body = self.response_body()
        self.assertIn('Allow: /llms.txt', body)
        self.assertIn('Allow: /llms-full.txt', body)

    def test_ai_answer_engines_are_explicitly_welcomed(self):
        body = self.response_body()
        for bot in ('GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended'):
            self.assertIn(f'User-agent: {bot}', body)

    def test_sitemap_directive_is_absolute(self):
        self.assertIn(f'Sitemap: {SITE_URL}/sitemap.xml', self.response_body())

    def test_no_invalid_llms_txt_directive(self):
        """`Llms-Txt:` is not part of RFC 9309 and makes validators report the file as malformed."""
        self.assertNotIn('Llms-Txt:', self.response_body())


class SitemapXmlTestCase(SeoFixtureMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_factory('owner_sitemap@test.com')
        self.published = self.create_listing('N-901')
        self.draft = self.create_listing('N-902', status=ListingStatus.DRAFT)

    def parsed(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/xml', response['Content-Type'])
        return response, ET.fromstring(response.content)

    def test_sitemap_is_well_formed_xml(self):
        _, root = self.parsed()
        self.assertTrue(root.tag.endswith('urlset'))

    def test_sitemap_lists_canonical_public_urls_only(self):
        _, root = self.parsed()
        namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locs = [loc.text for loc in root.findall('sm:url/sm:loc', namespace)]
        self.assertIn(f'{SITE_URL}/', locs)
        self.assertIn(f'{SITE_URL}/listings/', locs)
        self.assertIn(f'{SITE_URL}/accounts/vip/', locs)
        self.assertIn(f'{SITE_URL}{self.published.get_absolute_url()}', locs)
        # Draft listings must never leak into the index.
        self.assertNotIn(f'{SITE_URL}{self.draft.get_absolute_url()}', locs)
        # Legacy duplicate VIP URLs are 301s, not sitemap entries.
        self.assertNotIn(f'{SITE_URL}/packages/', locs)
        self.assertNotIn(f'{SITE_URL}/pricing/', locs)

    def test_listing_entries_carry_iso8601_lastmod(self):
        response, _ = self.parsed()
        body = response.content.decode('utf-8')
        loc = f'{SITE_URL}{self.published.get_absolute_url()}'
        match = re.search(r'<loc>%s</loc>\s*<lastmod>([^<]+)</lastmod>' % re.escape(loc), body)
        self.assertIsNotNone(match, 'listing entry is missing <lastmod>')
        self.assertRegex(match.group(1), r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_image_extension_is_declared(self):
        response, _ = self.parsed()
        body = response.content.decode('utf-8')
        self.assertIn('http://www.google.com/schemas/sitemap-image/1.1', body)
        self.assertIn('<image:loc>', body)


class VipLandingConsolidationTestCase(TestCase):
    """Three URLs used to serve identical VIP pricing content — one canonical wins."""

    def setUp(self):
        self.client = Client()

    def test_packages_redirects_permanently_to_vip(self):
        response = self.client.get('/packages/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/accounts/vip/')

    def test_pricing_redirects_permanently_to_vip(self):
        response = self.client.get('/pricing/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/accounts/vip/')

    def test_vip_page_exposes_product_offers_structdata(self):
        body = self.client.get('/accounts/vip/').content.decode('utf-8')
        self.assertIn('"@type": "Product"', body)
        self.assertIn('"price": "1000"', body)
        self.assertIn('"price": "5000"', body)
        self.assertIn('"priceCurrency": "THB"', body)


class StructuredDataAccuracyTestCase(SeoFixtureMixin, TestCase):
    """schema.org values must be derived from data, never hardcoded."""

    def setUp(self):
        self.client = Client()
        self.owner_factory('owner_schema@test.com')
        self.listing = self.create_listing('N-955')

    def test_offer_validity_is_rolling_not_hardcoded(self):
        body = self.client.get(self.listing.get_absolute_url()).content.decode('utf-8')
        self.assertNotIn('"priceValidUntil": "2027-12-31"', body)
        expected = (self.listing.updated_at + timedelta(days=365)).date().isoformat()
        self.assertIn(f'"priceValidUntil": "{expected}"', body)

    def test_availability_tracks_listing_status(self):
        self.assertEqual(self.listing.schema_availability, 'https://schema.org/InStock')
        self.listing.status = ListingStatus.CLOSED
        self.assertEqual(self.listing.schema_availability, 'https://schema.org/SoldOut')
        self.listing.status = ListingStatus.UNDER_NEGOTIATION
        self.assertEqual(
            self.listing.schema_availability, 'https://schema.org/LimitedAvailability'
        )

    def test_listing_detail_emits_breadcrumb_and_seller_organization(self):
        body = self.client.get(self.listing.get_absolute_url()).content.decode('utf-8')
        self.assertIn('"@type": "BreadcrumbList"', body)
        self.assertIn('"@type": "RealEstateListing"', body)
        self.assertIn(f'"@id": "{SITE_URL}/#organization"', body)

    def test_listing_without_photo_falls_back_to_og_cover(self):
        body = self.client.get(self.listing.get_absolute_url()).content.decode('utf-8')
        self.assertIn(f'"image": ["{SITE_URL}/static/images/og-cover.png"]', body)

    def test_marketplace_emits_itemlist_for_visible_listings(self):
        body = self.client.get('/listings/').content.decode('utf-8')
        self.assertIn('"@type": "ItemList"', body)
        self.assertIn(f'"{SITE_URL}{self.listing.get_absolute_url()}"', body)

    def test_about_and_contact_pages_expose_page_structdata(self):
        about = self.client.get('/about/').content.decode('utf-8')
        self.assertIn('"@type": "AboutPage"', about)
        contact = self.client.get('/contact/').content.decode('utf-8')
        self.assertIn('"@type": "ContactPage"', contact)
        self.assertIn('"+66876661778"', contact)


class OgCoverAssetTestCase(TestCase):
    """base.html, sitemap.xml and JSON-LD all reference this file — it must really exist."""

    def test_og_cover_exists_with_ogp_dimensions(self):
        path = Path(settings.BASE_DIR) / 'static' / 'images' / 'og-cover.png'
        self.assertTrue(path.exists(), 'static/images/og-cover.png is missing')
        self.assertEqual(png_dimensions(path), (1200, 630))

    def test_home_page_references_og_cover(self):
        body = Client().get('/').content.decode('utf-8')
        self.assertIn(f'{SITE_URL}/static/images/og-cover.png', body)


class JsonLdValidityTestCase(SeoFixtureMixin, TestCase):
    """
    WHY: A single stray comma or an unescaped quote inside a Django `{% if %}` branch
    produces invalid JSON-LD that Google silently discards — structured data breaks
    quietly, with no visible symptom on the page. Parsing every block catches that.
    """

    JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

    def setUp(self):
        self.client = Client()
        self.owner_factory('owner_jsonld@test.com')
        self.listing = self.create_listing('N-960')

    def assert_valid_json_ld(self, url):
        body = self.client.get(url).content.decode('utf-8')
        blocks = self.JSON_LD_RE.findall(body)
        self.assertGreaterEqual(len(blocks), 1, f'no JSON-LD found on {url}')
        for block in blocks:
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                self.fail(f'invalid JSON-LD on {url}: {exc}\n---\n{block}')

    def test_public_pages_emit_parseable_json_ld(self):
        urls = [
            '/',
            '/listings/',
            '/accounts/vip/',
            '/about/',
            '/contact/',
            '/privacy-policy/',
            '/terms-of-service/',
            self.listing.get_absolute_url(),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assert_valid_json_ld(url)


class CoreWebVitalsTestCase(TestCase):
    """
    LCP / CLS guards for the two highest-traffic templates.

    WHY: these regressions are invisible in functional tests — the page still renders
    correctly while LCP silently doubles (a 536 KB hero JPEG) or the browser pays an
    extra DNS+TLS round trip per third-party origin before anything can paint.
    """

    def setUp(self):
        self.client = Client()

    def body(self, path='/'):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.content.decode('utf-8')

    def test_every_third_party_origin_is_preconnected(self):
        body = self.body()
        for origin in (
            'https://fonts.googleapis.com',
            'https://fonts.gstatic.com',
            'https://cdn.tailwindcss.com',
            'https://unpkg.com',
        ):
            with self.subTest(origin=origin):
                self.assertIn(f'rel="preconnect" href="{origin}"', body)

    def test_icon_library_is_pinned_to_an_exact_version(self):
        """`@latest` costs a 302 on every cold cache and defeats immutable caching."""
        body = self.body()
        self.assertNotIn('lucide@latest', body)
        self.assertRegex(body, r'lucide@\d+\.\d+\.\d+')

    def test_lcp_hero_uses_webp_srcset_with_explicit_dimensions(self):
        for path in ('/', '/listings/'):
            with self.subTest(path=path):
                body = self.body(path)
                self.assertIn('hero_banner-800.webp 800w', body)
                self.assertIn('type="image/webp"', body)
                # Explicit intrinsic size → the box is reserved before the bytes land (CLS = 0).
                self.assertIn('width="1600"', body)
                self.assertIn('height="1200"', body)

    def test_home_hero_is_the_priority_lcp_image(self):
        self.assertIn('fetchpriority="high"', self.body())

    def test_hero_webp_variants_exist_and_beat_the_original_jpeg(self):
        images = Path(settings.BASE_DIR) / 'static' / 'images'
        for name in ('hero_banner-800.webp', 'hero_banner-1200.webp', 'hero_banner-1600.webp'):
            with self.subTest(name=name):
                self.assertTrue((images / name).exists(), f'{name} is missing — run scripts/optimize_hero_images.py')

        mobile_variant = (images / 'hero_banner-800.webp').stat().st_size
        original = (images / 'hero_banner.jpg').stat().st_size
        self.assertLess(mobile_variant, 200 * 1024, 'mobile hero WebP must stay under 200 KB')
        self.assertLess(
            (images / 'hero_banner-1200.jpg').stat().st_size,
            original,
            'the JPEG fallback must be lighter than the untouched source',
        )


class AiCitationContentTestCase(TestCase):
    """
    AEO / GEO: answer engines can only cite what they can quote verbatim.

    WHY: llms.txt and llms-full.txt are the two files crawlers read OUTSIDE the HTML
    flow. If they drift from the rendered pages — or keep naming a different domain —
    the model attributes the facts to someone else's site.
    """

    def setUp(self):
        self.client = Client()

    def body(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.content.decode('utf-8')

    def test_llms_txt_carries_canonical_origin_and_citation_rules(self):
        body = self.body('/llms.txt')
        self.assertIn(f'{SITE_URL}/', body)
        self.assertIn('การอ้างอิงหน้านี้', body)
        self.assertIn('ข้อเท็จจริงหลัก', body)

    def test_llms_full_carries_a_facts_table_and_suggested_citation(self):
        body = self.body('/llms-full.txt')
        self.assertIn('Canonical Facts & Citation', body)
        self.assertIn('Suggested citation', body)
        self.assertIn(f'{SITE_URL}/llms.txt', body)

    def test_no_page_or_ai_file_names_the_competing_domain(self):
        for path in ('/', '/llms.txt', '/llms-full.txt', '/robots.txt', '/about/', '/contact/'):
            with self.subTest(path=path):
                self.assertNotIn('sengranduan.com', self.body(path))

    def test_home_exposes_a_machine_readable_key_facts_block(self):
        body = self.body('/')
        self.assertIn('id="key-facts"', body)
        self.assertIn('SpeakableSpecification', body)
        self.assertIn('#key-facts', body)


class OrganizationSchemaTestCase(TestCase):
    """Entity signals that let a search/AI engine disambiguate the brand."""

    def setUp(self):
        self.body_text = Client().get('/').content.decode('utf-8')

    def test_organization_graph_ids_are_reused_across_nodes(self):
        for node_id in ('#organization', '#website', '#logo'):
            with self.subTest(node_id=node_id):
                self.assertIn(f'"{SITE_URL}/{node_id}"', self.body_text)

    def test_organization_declares_disambiguation_signals(self):
        for key in ('"alternateName"', '"knowsAbout"', '"slogan"', '"currenciesAccepted"', '"areaServed"'):
            with self.subTest(key=key):
                self.assertIn(key, self.body_text)

    def test_website_declares_site_search_action(self):
        self.assertIn('"@type": "SearchAction"', self.body_text)
        self.assertIn('q={search_term_string}', self.body_text)





