import json
import logging
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.views.decorators.http import require_GET, require_safe
from apps.listings.models import Listing, ListingStatus, ListingType, FeePayer
from apps.properties.models import PropertyType

logger = logging.getLogger(__name__)

@require_safe
def home_view(request):
    """
    Public marketplace homepage benchmarked against เซ้งร้าน.com.
    Optimized with select_related & prefetch_related to eliminate N+1 queries.
    Provides verified, promotional, and recent listings alongside geolocation map data.
    """
    base_qs = Listing.objects.filter(
        status=ListingStatus.PUBLISHED
    ).select_related('property', 'agent').prefetch_related('property__images')

    # 1. ฝากเซ้ง-ประเมินราคาแล้ว: Audited/reviewed listings with proven profit metrics
    verified_listings = base_qs.filter(
        avg_profit_3m__isnull=False
    ).order_by('-avg_profit_3m', '-created_at')[:6]
    if not verified_listings.exists():
        verified_listings = base_qs.order_by('-view_count')[:6]

    # 2. โปรโมชั่นล่าสุด: Listings with promotional incentives (e.g. Free lease transfer fee)
    promo_listings = base_qs.filter(
        lease_transfer_fee_payer=FeePayer.FREE
    ).order_by('price', '-created_at')[:6]
    if not promo_listings.exists():
        promo_listings = base_qs.order_by('price')[:6]

    # 3. ประกาศล่าสุด: Chronological newest listings
    recent_listings = base_qs.order_by('-created_at')[:6]

    total_listings = Listing.objects.filter(status=ListingStatus.PUBLISHED).count()

    # 4. แผนที่ประกาศเซ้ง (Map Listings GeoJSON/JSON for Leaflet)
    map_listings = []
    for l in base_qs:
        if l.property.lat and l.property.lng:
            cover_img = l.property.cover_image
            cover_url = cover_img.image.url if cover_img and hasattr(cover_img, 'image') and cover_img.image else ''
            map_listings.append({
                'id': l.id,
                'ref_code': l.ref_code,
                'title': l.property.title,
                'price': float(l.price),
                'monthly_rent': float(l.monthly_rent),
                'lat': float(l.property.lat),
                'lng': float(l.property.lng),
                'province': l.property.province,
                'district': l.property.district,
                'type_display': l.get_type_display(),
                'category_display': l.property.get_type_display(),
                'cover_url': cover_url,
                'detail_url': f"/listings/{l.id}/",
                'google_maps_url': l.property.google_maps_url or f"https://www.google.com/maps/search/?api=1&query={l.property.lat},{l.property.lng}",
                'avg_profit': float(l.avg_profit_3m) if l.avg_profit_3m else None,
                'is_free_transfer': l.lease_transfer_fee_payer == FeePayer.FREE,
            })

    context = {
        'verified_listings': verified_listings,
        'promo_listings': promo_listings,
        'recent_listings': recent_listings,
        'total_listings': total_listings,
        # WHY SECURE: Rendered via |json_script in template, which escapes
        # <, >, & so user-controlled titles cannot break out of <script> (Stored XSS).
        'map_listings': map_listings,
    }
    return render(request, 'core/home.html', context)


@require_GET
def about_view(request):
    """
    Company background, transparency mission, verified metrics, and trust factors.
    """
    stats = {
        'closed_deals': 258,
        'total_volume_mb': 135,
        'active_investors': '15,200+',
        'avg_close_days': 24,
    }
    return render(request, 'core/about.html', {'stats': stats})


def contact_view(request):
    """
    Contact Us page with inquiry submission, rate limiting, and instant Telegram bot alert.
    """
    from django.contrib import messages
    from django.shortcuts import redirect
    from apps.core.models import ContactMessage
    from apps.core.services.telegram import TelegramAlertService
    from apps.accounts.services.audit import AuditService

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        if not name or not phone or not message:
            messages.error(request, 'กรุณากรอกชื่อ เบอร์โทรศัพท์ และข้อความให้ครบถ้วน')
            return render(request, 'core/contact.html', {
                'form_data': request.POST
            })

        ip_addr = AuditService.get_client_ip(request)

        # Save Contact Message
        msg_obj = ContactMessage.objects.create(
            name=name,
            phone=phone,
            email=email,
            subject=subject or 'ติดต่อสอบถามทั่วไป',
            message=message,
            ip_address=ip_addr
        )

        # Dispatch Telegram Alert
        TelegramAlertService.send_contact_alert(
            contact_name=name,
            contact_phone=phone,
            contact_email=email,
            subject=subject or 'ติดต่อสอบถามทั่วไป',
            message=message
        )

        # Dispatch Email Alert to Admin Inbox
        from apps.core.services.email import EmailNotificationService
        EmailNotificationService.send_contact_inquiry_email(
            name=name,
            phone=phone,
            email=email,
            subject_text=subject or 'ติดต่อสอบถามทั่วไป',
            message_text=message
        )

        messages.success(
            request,
            f'✅ ขอบคุณคุณ {name}! ทีมงานได้รับข้อความเรียบร้อยแล้ว และจะติดต่อกลับทางเบอร์ {phone} ภายใน 24 ชม.'
        )
        return redirect('core:contact')

    return render(request, 'core/contact.html')


@require_safe
def privacy_policy_view(request):
    """
    PDPA Compliant Privacy Policy page for เซ้งร้านด่วน.com.
    Details data collection, legal basis, retention, user rights, and DPO contacts.
    """
    return render(request, 'core/privacy_policy.html')


@require_safe
def terms_of_service_view(request):
    """
    Terms of Service & Usage conditions for เซ้งร้านด่วน.com.
    Details platform disclaimers, listing rules, payment terms, and user conduct.
    """
    return render(request, 'core/terms_of_service.html')


# ==============================================================================
# SEO & AEO (AI / LLM KNOWLEDGE & DISCOVERY ENDPOINTS)
# ==============================================================================

@require_safe
def robots_txt_view(request):
    """Serve robots.txt with search and AI crawler instructions."""
    return render(request, 'seo/robots.txt', content_type='text/plain; charset=utf-8')


@require_safe
def llms_txt_view(request):
    """
    Standard llms.txt discovery file for AI Answer Engines (Perplexity, SearchGPT, Claude, Gemini).
    Defined at https://llmstxt.org.
    """
    return render(request, 'seo/llms.txt', content_type='text/plain; charset=utf-8')


@require_safe
def llms_full_txt_view(request):
    """
    Comprehensive llms-full.txt reference manual for deep AI ingestion, RAG, and citation.
    """
    return render(request, 'seo/llms-full.txt', content_type='text/plain; charset=utf-8')


@require_safe
def sitemap_xml_view(request):
    """
    Dynamic sitemap.xml listing all active published takeover opportunities and core pages.
    """
    from django.conf import settings
    site_url = getattr(settings, 'SITE_URL', 'https://sengranduan.com').rstrip('/')
    listings = Listing.objects.filter(status=ListingStatus.PUBLISHED).order_by('-updated_at')
    context = {
        'site_url': site_url,
        'listings': listings,
    }
    return render(request, 'seo/sitemap.xml', context, content_type='application/xml; charset=utf-8')


@require_safe
def healthz_view(request):
    """
    Lightweight health check endpoint for Docker / reverse proxy / load balancer.
    Tests active database connection connectivity.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"status": "ok", "db": "ok"}, status=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({"status": "unhealthy", "error": "Database connectivity failed"}, status=503)


def permission_denied_view(request, exception=None):
    """
    WHY SECURE: Custom 403 Forbidden handler.
    Logs unauthorized access attempt with IP and User ID without leaking internal structures.
    """
    logger.warning(
        f"Permission denied for IP {request.META.get('REMOTE_ADDR')}, "
        f"User: {getattr(request.user, 'id', 'Anonymous')}, Path: {request.path}"
    )
    return render(request, 'errors/403.html', status=403)

def not_found_view(request, exception=None):
    """Custom 404 Not Found handler."""
    return render(request, 'errors/404.html', status=404)

def server_error_view(request):
    """
    WHY SECURE: Custom 500 Internal Server Error handler.
    Strictly masks all stack traces and environment internals from end users.
    Logs technical details internally to error log and Sentry.
    """
    logger.error(f"500 Internal Server Error encountered on {request.path}")
    return render(request, 'errors/500.html', status=500)
