from django import template
from django.utils.safestring import mark_safe

from apps.core.utils.html import linkify_rich_html

register = template.Library()


@register.filter
def linkify_urls(value):
    """
    Make bare URLs in an already-sanitized description clickable at display time,
    so descriptions saved before auto-linking existed get links too.
    """
    return mark_safe(linkify_rich_html(str(value or '')))
