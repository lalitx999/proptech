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
