import re

from django.utils.html import escape, strip_tags

import bleach
from bleach.linkifier import Linker

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
        clean = bleach.clean(raw, tags=RICH_TEXT_TAGS, attributes=RICH_TEXT_ATTRS, strip=True, **kwargs)
    except Exception:
        return escape(strip_tags(raw))
    return linkify_rich_html(clean)


# Only explicit links (http(s):// or www.) so prices like "1.5" or words like "test.py"
# stay text. ASCII-only, so Thai text written right after a URL is not swallowed
# ("ดูที่https://lin.ee/abcเลย" links only https://lin.ee/abc).
LINKIFY_URL_RE = re.compile(
    r"(?:https?://|www\.)[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::\d+)?"
    r"(?:[/?#][a-z0-9\-._~%!$&'()*+,;=:@/?#]*)?",
    re.IGNORECASE,
)


def _external_link_attrs(attrs, new=False):
    attrs[(None, 'target')] = '_blank'
    attrs[(None, 'rel')] = 'noopener noreferrer nofollow'
    return attrs


def linkify_rich_html(html):
    """
    Turn bare URLs (typed or pasted as plain text) into clickable links.
    Existing <a> tags are kept; text inside them is not linked twice.
    Input must already be sanitized: this only adds <a href="http(s)://..."> tags.
    """
    if not html:
        return ''
    try:
        linker = Linker(url_re=LINKIFY_URL_RE, parse_email=False, callbacks=[_external_link_attrs])
        return linker.linkify(html)
    except Exception:
        return html
