from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from apps.accounts.permissions import role_required, can_view, can_edit, can_delete, get_scoped_queryset
from apps.accounts.models import UserRole
from apps.accounts.services.audit import AuditService
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingStatus, ListingApproval, ListingType
from apps.listings.forms import ListingForm, ListingApprovalForm
from apps.listings.services.search import ListingSearchService

# ==============================================================================
# PUBLIC MARKETPLACE & HTMX SEARCH (RATE LIMITED: 60/min/IP)
# ==============================================================================
@ratelimit(key='ip', rate='60/m', block=True)
@require_http_methods(["GET"])
def marketplace_view(request):
    """
    WHY SECURE:
    1. Rate limited to 60 queries/min to thwart scraping and ReDoS attacks.
    2. Input parameters sanitized via ListingSearchService.
    3. Seamless HTMX partial rendering: returns only the card grid if requested by HTMX.
    """
    queryset = ListingSearchService.search(request.GET)
    paginator = Paginator(queryset, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # WHY SEO CRITICAL: Faceted/filtered search result URLs (?q=...&province=...&price_min=...)
    # are programmatically infinite duplicates of the canonical /listings/ document. They are
    # served as `noindex, follow` with a canonical pointing at /listings/ so link equity
    # consolidates on the one page that should rank. Pure pagination stays indexable with a
    # self-referencing canonical.
    filter_keys = (
        'q', 'type', 'category', 'property_type', 'province', 'district',
        'price_min', 'price_max', 'rent_min', 'rent_max',
    )
    has_filters = any(request.GET.get(key) for key in filter_keys)

    context = {
        'page_obj': page_obj,
        'listings': page_obj.object_list,
        'total_count': paginator.count,
        'listing_types': ListingType.choices,
        'property_types': PropertyType.choices,
        'current_params': request.GET.dict(),
        'seo_has_filters': has_filters,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'listings/partials/listings_grid.html', context)
    return render(request, 'listings/marketplace.html', context)

@login_required
@role_required(UserRole.CUSTOMER, UserRole.OWNER, UserRole.AGENT, UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET"])
def listing_list_view(request):
    """
    WHY SECURE:
    Uses get_scoped_queryset to guarantee owner isolation.
    """
    listings = get_scoped_queryset(
        request.user,
        Listing.objects.select_related('property', 'agent').prefetch_related('property__images')
    )
    return render(request, 'listings/listing_list.html', {'listings': listings})

import logging
from decimal import Decimal, InvalidOperation
logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET", "POST"])
def consignment_wizard_view(request):
    """
    Multi-Step Listing Creation Wizard (Consignment):
    Step 1: Contact & Location (Title, Type, Province, District, Address, Maps Link)
    Step 2: Financials & Lease (Takeover Price, Rent, Deposit, Lease Months, Transfer Fee, 3M Revenue/Profit)
    Step 3: Specifications & Assets (Area Sqm, Floors, Description, Included Equipment, Retained Staff)
    Step 4: Image Uploads & Review

    Quota Rules:
    - Free member: 1 post / calendar month
    - VIP member: 4 posts / calendar month
    - If user has no remaining quota, renders template with quota_exceeded=True and shows VIP upgrade modal.
    """
    user = request.user
    can_post = user.can_post_listing()
    remaining_quota = user.get_remaining_quota()
    monthly_quota = user.get_monthly_quota()
    posted_count = user.get_current_month_posts_count()

    # Block free users who exceeded their quota
    if user.role not in [UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT]:
        if not can_post:
            messages.warning(
                request,
                '⚠️ คุณได้ใช้สิทธิ์ลงประกาศฟรีประจำเดือนนี้ครบแล้ว (จำกัด 1 ร้านค้าต่อเดือน) '
                'กรุณาอัปเกรดเป็นสมาชิก VIP เพื่อลงประกาศเพิ่มได้ทันที'
            )
            return redirect('accounts:vip_membership')

    if request.method == 'POST':
        if not can_post:
            messages.error(request, 'คุณได้ใช้สิทธิ์ลงประกาศประจำเดือนนี้ครบแล้ว กรุณาอัปเกรดเป็นสมาชิก VIP เพื่อรับสิทธิ์เพิ่ม')
            return redirect('accounts:vip_membership')

        title = request.POST.get('title', '').strip()
        prop_type = request.POST.get('property_type', PropertyType.RETAIL_SHOP)
        province = request.POST.get('province', '').strip()
        district = request.POST.get('district', '').strip()
        postal = request.POST.get('postal', '10000').strip()
        address = request.POST.get('address', '').strip()
        maps_link = request.POST.get('google_maps_link', '').strip()

        # Parse financials
        try:
            price = Decimal(request.POST.get('price', '0'))
            if price <= 0:
                raise ValueError("ราคาเซ้งต้องมากกว่า 0 บาท")
        except (ValueError, InvalidOperation):
            messages.error(request, 'กรุณาระบุราคาเซ้งที่ถูกต้อง (มากกว่า 0 บาท)')
            return redirect('listings:listing_create')

        try:
            monthly_rent = Decimal(request.POST.get('monthly_rent', '0') or '0')
        except (ValueError, InvalidOperation):
            monthly_rent = Decimal('0')

        try:
            security_deposit = Decimal(request.POST.get('security_deposit', '0') or '0')
        except (ValueError, InvalidOperation):
            security_deposit = Decimal('0')

        try:
            lease_months = int(request.POST.get('lease_remaining_months', '12') or '12')
        except ValueError:
            lease_months = 12

        try:
            lease_transfer_fee = Decimal(request.POST.get('lease_transfer_fee', '0') or '0')
        except (ValueError, InvalidOperation):
            lease_transfer_fee = Decimal('0')

        from apps.listings.models import FeePayer
        fee_payer = request.POST.get('lease_transfer_fee_payer', FeePayer.FREE)

        # Revenue & Profit
        avg_revenue = None
        rev_raw = request.POST.get('avg_revenue_3m', '').strip()
        if rev_raw:
            try:
                avg_revenue = Decimal(rev_raw)
            except (ValueError, InvalidOperation):
                avg_revenue = None

        avg_profit = None
        profit_raw = request.POST.get('avg_profit_3m', '').strip()
        if profit_raw:
            try:
                avg_profit = Decimal(profit_raw)
            except (ValueError, InvalidOperation):
                avg_profit = None

        # Dimensions & Specs
        try:
            area_sqm = Decimal(request.POST.get('area_sqm', '0') or '0')
        except (ValueError, InvalidOperation):
            area_sqm = Decimal('0')

        try:
            floors = int(request.POST.get('floors', '1') or '1')
        except ValueError:
            floors = 1

        desc = request.POST.get('desc', '').strip()
        includes_equipment = request.POST.get('includes_equipment', '').strip()
        includes_staff = request.POST.get('includes_staff') in ['true', 'on', '1']

        # Google Maps URL & Coordinates
        google_maps_url = (request.POST.get('google_maps_link') or request.POST.get('google_maps_url') or '').strip()
        lat = None
        lng = None
        lat_raw = request.POST.get('lat', '').strip()
        lng_raw = request.POST.get('lng', '').strip()
        if lat_raw and lng_raw:
            try:
                lat = Decimal(lat_raw)
                lng = Decimal(lng_raw)
            except (ValueError, InvalidOperation):
                lat = None
                lng = None

        from apps.properties.utils import extract_google_maps_coordinates, get_default_coordinates_for_location
        if (not lat or not lng) and google_maps_url:
            ext_lat, ext_lng = extract_google_maps_coordinates(google_maps_url)
            if ext_lat and ext_lng:
                lat = ext_lat
                lng = ext_lng

        if not lat or not lng:
            lat, lng = get_default_coordinates_for_location(province, district)

        # 1. Create Property
        property_obj = Property.objects.create(
            owner=user,
            type=prop_type,
            title=title or f"เซ้งร้าน ย่าน {district} {province}",
            desc=desc or f"เซ้งร้าน {title} ทำเลศักยภาพสูง {district} {province}",
            address=address,
            province=province,
            district=district,
            postal=postal,
            google_maps_url=google_maps_url or None,
            lat=lat,
            lng=lng,
            area_sqm=area_sqm,
            floors=floors
        )

        # 2. Upload and sanitize Images
        from apps.core.utils.files import validate_and_sanitize_image
        from apps.properties.models import PropertyImage

        uploaded_images = request.FILES.getlist('images')
        for idx, img_file in enumerate(uploaded_images):
            try:
                sanitized_file = validate_and_sanitize_image(img_file)
                PropertyImage.objects.create(
                    property=property_obj,
                    image=sanitized_file,
                    is_cover=(idx == 0),
                    order=idx
                )
            except Exception as e:
                logger.warning(f"Failed to process image {img_file.name}: {e}")

        # 3. Contact Info
        contact_phone = request.POST.get('contact_phone', '').strip()
        contact_line_id = request.POST.get('contact_line_id', '').strip()
        if not contact_phone:
            contact_phone = user.phone or ''
        if not contact_line_id:
            contact_line_id = getattr(user, 'line_id', '') or ''

        # Auto-update user phone and line_id if empty
        user_updated_fields = []
        if contact_phone and not user.phone:
            user.phone = contact_phone
            user_updated_fields.append('phone')
        if contact_line_id and not getattr(user, 'line_id', ''):
            user.line_id = contact_line_id
            user_updated_fields.append('line_id')
        if user_updated_fields:
            user.save(update_fields=user_updated_fields)

        # 4. Create Listing
        listing = Listing.objects.create(
            property=property_obj,
            type=ListingType.TAKEOVER,
            price=price,
            monthly_rent=monthly_rent,
            security_deposit=security_deposit,
            lease_remaining_months=lease_months,
            lease_transfer_fee=lease_transfer_fee,
            lease_transfer_fee_payer=fee_payer,
            avg_revenue_3m=avg_revenue,
            avg_profit_3m=avg_profit,
            includes_equipment=includes_equipment,
            includes_staff=includes_staff,
            contact_phone=contact_phone,
            contact_line_id=contact_line_id,
            status=ListingStatus.PUBLISHED,
            published_at=timezone.now()
        )

        # Audit Log
        AuditService.log(
            action='CREATE',
            model_name='Listing',
            object_id=listing.pk,
            changes={'ref_code': listing.ref_code, 'price': str(price), 'title': property_obj.title},
            request=request
        )

        # Dispatch Telegram Alert for New Listing!
        from apps.core.services.telegram import TelegramAlertService
        TelegramAlertService.send_new_listing_alert(listing)

        messages.success(request, f'🎉 สร้างประกาศเซ้งร้านรหัส {listing.ref_code} สำเร็จแล้ว!')
        return redirect('listings:listing_detail', pk=listing.pk)

    from apps.listings.models import FeePayer
    context = {
        'quota_exceeded': not can_post,
        'remaining_quota': remaining_quota,
        'monthly_quota': monthly_quota,
        'posted_count': posted_count,
        'property_types': PropertyType.choices,
        'fee_payer_choices': FeePayer.choices,
    }
    return render(request, 'listings/consignment_wizard.html', context)


@login_required
@role_required(UserRole.CUSTOMER, UserRole.OWNER, UserRole.AGENT, UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET", "POST"])
def listing_create_view(request, property_pk):
    """
    WHY SECURE:
    Verifies that request.user actually owns the specified property (anti-IDOR).
    """
    property_obj = get_object_or_404(Property, pk=property_pk)
    if not (request.user.is_admin() or request.user.is_staff_member() or property_obj.owner == request.user):
        raise PermissionDenied("คุณสามารถสร้างประกาศได้เฉพาะทรัพย์สินที่คุณเป็นเจ้าของเท่านั้น")

    if request.user.role not in [UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT]:
        if not request.user.can_post_listing():
            messages.warning(
                request,
                '⚠️ คุณได้ใช้สิทธิ์ลงประกาศฟรีประจำเดือนนี้ครบแล้ว (จำกัด 1 ร้านค้าต่อเดือน) '
                'กรุณาอัปเกรดเป็นสมาชิก VIP เพื่อลงประกาศเพิ่มได้ทันที'
            )
            return redirect('accounts:vip_membership')

    if request.method == 'POST':
        form = ListingForm(request.POST)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.property = property_obj
            if request.user.role == UserRole.AGENT:
                listing.agent = request.user
            listing.status = ListingStatus.PUBLISHED
            listing.published_at = timezone.now()
            listing.save()

            # Handle uploaded images if provided
            uploaded_images = request.FILES.getlist('images')
            if uploaded_images:
                from apps.core.utils.files import validate_and_sanitize_image
                from apps.properties.models import PropertyImage
                existing_count = property_obj.images.count()
                for idx, img_file in enumerate(uploaded_images):
                    try:
                        sanitized_file = validate_and_sanitize_image(img_file)
                        PropertyImage.objects.create(
                            property=property_obj,
                            image=sanitized_file,
                            is_cover=(idx == 0 and existing_count == 0),
                            order=existing_count + idx
                        )
                    except Exception as e:
                        logger.warning(f"Failed to process image {img_file.name}: {e}")

            AuditService.log(
                action='CREATE',
                model_name='Listing',
                object_id=listing.pk,
                changes={'ref_code': listing.ref_code, 'price': str(listing.price)},
                request=request
            )

            # Dispatch Telegram Alert
            from apps.core.services.telegram import TelegramAlertService
            TelegramAlertService.send_new_listing_alert(listing)

            messages.success(request, f'🎉 ประกาศเซ้งร้านรหัส {listing.ref_code} เผยแพร่ขึ้นหน้าเว็บไซต์เรียบร้อยแล้ว!')
            return redirect('listings:listing_detail', pk=listing.pk)
    else:
        form = ListingForm()

    return render(request, 'listings/listing_form.html', {'form': form, 'property': property_obj})

@require_http_methods(["GET"])
def listing_detail_view(request, pk):
    """
    WHY SECURE:
    Public can only view if published.
    Owner/Agent/Staff can view drafts.
    """
    listing = get_object_or_404(
        Listing.objects.select_related('property', 'property__owner', 'agent')
        .prefetch_related('property__images'),
        pk=pk
    )
    if not can_view(request.user, listing):
        raise PermissionDenied("ประกาศนี้ยังไม่เปิดเผยต่อสาธารณะ")

    # Increment view count safely
    Listing.objects.filter(pk=pk).update(view_count=listing.view_count + 1)

    from apps.leads.forms import LeadInquiryForm
    lead_form = LeadInquiryForm()

    related_listings = Listing.objects.filter(
        status=ListingStatus.PUBLISHED,
        property__province=listing.property.province
    ).exclude(pk=listing.pk).select_related('property').prefetch_related('property__images')[:4]

    context = {
        'listing': listing,
        'lead_form': lead_form,
        'related_listings': related_listings,
    }

    return render(request, 'listings/listing_detail.html', context)

@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET", "POST"])
def listing_approval_view(request, pk):
    """
    WHY SECURE:
    Only Staff/Admin can approve or reject listings.
    Records immutable ListingApproval log and triggers state change.
    """
    listing = get_object_or_404(Listing.objects.select_related('property'), pk=pk)

    if request.method == 'POST':
        form = ListingApprovalForm(request.POST)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.listing = listing
            approval.reviewer = request.user
            approval.save()

            # State transition
            if approval.action == ListingApproval.Action.APPROVE:
                listing.status = ListingStatus.PUBLISHED
                listing.published_at = timezone.now()
            elif approval.action == ListingApproval.Action.REJECT:
                listing.status = ListingStatus.REJECTED
            elif approval.action == ListingApproval.Action.REQUEST_CHANGES:
                listing.status = ListingStatus.DRAFT

            listing.save(update_fields=['status', 'published_at'])

            AuditService.log(
                action='UPDATE',
                model_name='Listing',
                object_id=listing.pk,
                changes={'status': listing.status, 'approval_action': approval.action, 'note': approval.note},
                request=request
            )
            messages.success(request, f'บันทึกผลการตรวจสอบประกาศ {listing.ref_code}: {approval.get_action_display()}')
            return redirect('listings:listing_detail', pk=listing.pk)
    else:
        form = ListingApprovalForm()

    return render(request, 'listings/listing_approval.html', {'form': form, 'listing': listing})


# ==============================================================================
# LISTING COMPARISON MATRIX & FAVORITES
# ==============================================================================
@require_http_methods(["GET"])
def listing_compare_view(request):
    """
    Side-by-side comparison matrix for up to 4 shop listings.
    URL: /listings/compare/?ids=1,2,3
    """
    raw_ids = request.GET.get('ids', '').strip()
    id_list = []
    if raw_ids:
        for part in raw_ids.split(','):
            part = part.strip()
            if part.isdigit():
                id_list.append(int(part))
    id_list = id_list[:4]

    listings = []
    if id_list:
        listings = list(
            Listing.objects.filter(id__in=id_list, status=ListingStatus.PUBLISHED)
            .select_related('property', 'property__owner')
            .prefetch_related('property__images')
        )
        # Preserve requested order
        listings.sort(key=lambda x: id_list.index(x.id) if x.id in id_list else 99)

    return render(request, 'listings/listing_compare.html', {
        'listings': listings,
        'compared_ids': [l.id for l in listings],
    })


@require_http_methods(["GET"])
def listing_favorites_view(request):
    """
    User favorites page (reads IDs from query params or localStorage).
    URL: /listings/favorites/?ids=1,2,3
    """
    raw_ids = request.GET.get('ids', '').strip()
    id_list = []
    if raw_ids:
        for part in raw_ids.split(','):
            part = part.strip()
            if part.isdigit():
                id_list.append(int(part))
    id_list = id_list[:30]

    listings = []
    if id_list:
        listings = Listing.objects.filter(id__in=id_list, status=ListingStatus.PUBLISHED).select_related(
            'property', 'property__owner'
        ).prefetch_related('property__images')

    return render(request, 'listings/listing_favorites.html', {
        'listings': listings,
        'total_count': len(listings) if isinstance(listings, list) else listings.count(),
    })
