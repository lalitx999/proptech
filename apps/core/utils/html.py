from django.utils.html import escape, strip_tags

import bleach

try:
    from bleach.css_sanitizer import CSSSanitizer
except ImportError:  # tinycss2 missing: style attributes are dropped instead
    CSSSanitizer = None

# ==============================================================================
# RICH TEXT (WYSIWYG) SANITIZER
# ==============================================================================
# Shared by every form that posts HTML from the rich text editor partial
# (templates/includes/rich_text_editor.html).
RICH_TEXT_TAGS = ['p', 'br', 'span', 'b', 'strong', 'i', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h3', 'h4', 'font', 'div']
RICH_TEXT_ATTRS = {
    'a': ['href', 'title', 'target', 'rel', 'class'],
    'span': ['style', 'class'],
    'font': ['color'],
    '*': ['style', 'class'],
}
RICH_TEXT_CSS = ['color', 'background-color', 'font-weight', 'text-decoration']


def sanitize_rich_html(raw):
    """
    WHY SECURE: The output is rendered with |safe on listing pages, so it must
    never contain script, event handlers or javascript: links. If sanitizing
    fails for any reason we fall back to escaped plain text (fail closed),
    never to the raw input.
    """
    if not raw:
        return ''
    try:
        kwargs = {}
        if CSSSanitizer is not None:
            kwargs['css_sanitizer'] = CSSSanitizer(allowed_css_properties=RICH_TEXT_CSS)
        return bleach.clean(raw, tags=RICH_TEXT_TAGS, attributes=RICH_TEXT_ATTRS, strip=True, **kwargs)
    except Exception:
        return escape(strip_tags(raw))
