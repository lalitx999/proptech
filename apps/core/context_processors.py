from django.conf import settings


def site_url(request):
    """
    Exposes the canonical public origin (e.g. https://www.xn--72ch2atb1d4a4f1fudfc.com) to all templates
    as {{ site_url }}. Configured via SITE_URL in the environment so the domain can be
    changed without touching templates.

    Also exposes the optional Search Console / Bing Webmaster verification tokens so
    base.html can render the verification meta tags without code changes.
    """
    return {
        'site_url': settings.SITE_URL,
        'site_name': getattr(settings, 'SITE_NAME', 'เซ้งร้านด่วน.com'),
        'google_site_verification': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
        'bing_site_verification': getattr(settings, 'BING_SITE_VERIFICATION', ''),
    }
