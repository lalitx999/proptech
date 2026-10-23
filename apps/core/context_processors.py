from django.conf import settings


def site_url(request):
    """
    Exposes the canonical public origin (e.g. https://sengranduan.com) to all templates
    as {{ site_url }}. Configured via SITE_URL in the environment so the domain can be
    changed without touching templates.
    """
    return {'site_url': settings.SITE_URL}
