import re
import logging
from django.http import HttpResponsePermanentRedirect
from django.urls import reverse
from apps.listings.models import Listing

logger = logging.getLogger(__name__)

class LegacyWordpressRedirectMiddleware:
    """
    WHY SECURE & SEO CRITICAL:
    1. Preserves 100% Google SEO PageRank and backlinks from the legacy WordPress site
       (เซ้งร้านด่วน.com / ?p=123 / /2024/01/post-name/ / Ref Codes like N-032).
    2. Issues HTTP 301 Permanent Redirects to corresponding new Django listing URLs.
    3. Prevents 404 bounce rates for prospective buyers clicking old social media or Google links.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.ref_code_pattern = re.compile(r'([A-Za-z]\s*[-_]?\s*\d{2,4})')

    def __call__(self, request):
        path = request.path
        query_string = request.META.get('QUERY_STRING', '')

        # 1. Match ?p=123 WordPress permalink
        if query_string:
            p_match = re.search(r'(?:^|&)p=(\d+)(?:&|$)', query_string)
            if p_match:
                return HttpResponsePermanentRedirect(reverse('listings:marketplace'))

        # 2. Check for Ref Code in legacy URL paths (e.g. /n-032/, /posts/s-228/)
        ref_match = self.ref_code_pattern.search(path)
        if ref_match and not path.startswith('/listings/'):
            raw_code = ref_match.group(1)
            # Normalize to format: N-032
            normalized_code = re.sub(r'\s+', '', raw_code).replace('_', '-').upper()
            if '-' not in normalized_code and len(normalized_code) >= 2:
                normalized_code = f"{normalized_code[0]}-{normalized_code[1:]}"

            listing = (
                Listing.objects.filter(ref_code__iexact=normalized_code).first() or
                Listing.objects.filter(ref_code__iexact=normalized_code.replace('-', '')).first()
            )
            if listing:
                logger.info(f"SEO 301 Redirect: Legacy Ref {raw_code} -> {listing.get_absolute_url()}")
                return HttpResponsePermanentRedirect(listing.get_absolute_url())

        # 3. Match /listing/xxx (WordPress legacy singular) -> /listings/ (New plural marketplace)
        if path.startswith('/listing/') and not path.startswith('/listings/'):
            return HttpResponsePermanentRedirect(reverse('listings:marketplace'))

        return self.get_response(request)


# ==============================================================================
# SEARCH-ENGINE INDEX CONTROL (META ROBOTS / X-ROBOTS-TAG)
# ==============================================================================
# WHY SEO CRITICAL:
# Authenticated dashboards, editing wizards and user-private pages must never be
# indexed. Instead of sprinkling `{% block robots %}` into a dozen templates we
# enforce it once, at the response layer, via the X-Robots-Tag HTTP header.
# Header-based directives are honoured by Googlebot, Bingbot and AI crawlers and
# are impossible to forget when a new private view is added under these prefixes.
SEO_NOINDEX_PREFIXES = (
    '/accounts/',          # login, register, 2FA, OTP, VIP slip management
    '/properties/',        # "my shops" CRUD
    '/contracts/',          # broker CRM / deal pipeline
    '/leads/',             # lead inboxes
    '/admin-dashboard/',   # internal command center
    '/dev-admin-only/',    # Django admin (dev only)
    '/listings/create/',   # consignment wizard
    '/listings/manage/',   # my listings
    '/listings/favorites/',# personal favourites
    '/listings/compare/',  # personal comparison matrix
)

# Public commercial landing pages that live *inside* the prefixes above and must
# stay indexable (they are also listed in sitemap.xml and llms.txt).
SEO_INDEXABLE_EXACT_PATHS = (
    '/accounts/vip',
)

# Private dynamic sub-paths (e.g. /listings/12/approve/)
SEO_NOINDEX_PATTERNS = (
    re.compile(r'^/listings/\d+/approve/?$'),
)


class SeoIndexControlMiddleware:
    """Adds `X-Robots-Tag: noindex` to private pages and to every 4xx/5xx response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _is_private(self, path):
        normalized = path.rstrip('/') or '/'
        if normalized in SEO_INDEXABLE_EXACT_PATHS:
            return False
        if any(path.startswith(prefix) for prefix in SEO_NOINDEX_PREFIXES):
            return True
        return any(pattern.match(path) for pattern in SEO_NOINDEX_PATTERNS)

    def __call__(self, request):
        response = self.get_response(request)

        # Only HTML documents carry meta/header indexing directives.
        if not response.get('Content-Type', '').startswith('text/html'):
            return response

        # Never override a directive that a view already set deliberately.
        if response.get('X-Robots-Tag'):
            return response

        if self._is_private(request.path) or response.status_code >= 400:
            response['X-Robots-Tag'] = 'noindex, nofollow'

        return response
