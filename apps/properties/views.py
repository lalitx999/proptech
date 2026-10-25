from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import role_required, can_view, can_edit, can_delete, get_scoped_queryset
from apps.accounts.models import UserRole
from apps.accounts.services.audit import AuditService
from apps.properties.models import Property, PropertyImage
from apps.properties.forms import PropertyForm, PropertyImageForm

@login_required
@role_required(UserRole.CUSTOMER, UserRole.OWNER, UserRole.AGENT, UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET"])
def property_list_view(request):
    """
    WHY SECURE: Row-level isolation.
    Uses get_scoped_queryset so owners only see their own properties.
    """
    properties = get_scoped_queryset(request.user, Property.objects.prefetch_related('images', 'listings'))
    return render(request, 'properties/property_list.html', {'properties': properties})

@login_required
@role_required(UserRole.CUSTOMER, UserRole.OWNER, UserRole.AGENT, UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET", "POST"])
def property_create_view(request):
    """
    WHY SECURE:
    Owner is firmly bound from request.user (cannot be spoofed from POST data).
    Enforces monthly listing quota so free users cannot bypass via property creation.
    """
    if request.user.role not in [UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT]:
        if not request.user.can_post_listing():
            messages.warning(
                request,
                '⚠️ คุณได้ใช้สิทธิ์ลงประกาศฟรีประจำเดือนนี้ครบแล้ว (จำกัด 1 ร้านค้าต่อเดือน) '
                'กรุณาอัปเกรดเป็นสมาชิก VIP เพื่อลงประกาศเพิ่มได้ทันที'
            )
            return redirect('accounts:vip_membership')

    if request.method == 'POST':
        form = PropertyForm(request.POST)
        if form.is_valid():
            property_obj = form.save(commit=False)
            property_obj.owner = request.user
            property_obj.save()

            AuditService.log(
                action='CREATE',
                model_name='Property',
                object_id=property_obj.pk,
                changes={'title': property_obj.title, 'type': property_obj.type},
                request=request
            )
            messages.success(request, 'เพิ่มข้อมูลสถานที่เรียบร้อยแล้ว! กรุณาระบุราคาเซ้งและรายละเอียดเพื่อลงประกาศ')
            return redirect('listings:listing_create_property', property_pk=property_obj.pk)
    else:
        form = PropertyForm()

    return render(request, 'properties/property_form.html', {'form': form, 'title': 'เพิ่มข้อมูลทรัพย์สินใหม่'})

@login_required
@require_http_methods(["GET"])
def property_detail_view(request, pk):
    """
    WHY SECURE:
    Enforces object-level can_view check. Raw PK in URL is verified against ownership.
    """
    property_obj = get_object_or_404(Property.objects.prefetch_related('images', 'listings'), pk=pk)
    if not can_view(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการเข้าดูข้อมูลทรัพย์สินนี้")
    return render(request, 'properties/property_detail.html', {'property': property_obj})

@login_required
@login_required
@require_http_methods(["GET", "POST"])
def property_update_view(request, pk):
    """
    WHY SECURE:
    Unified Edit View for Admin & Property Owner:
    - Same complete 2-column structure as Fast Post / New Post
    - Full photo management: view thumbnails, delete photo, set cover, upload additional photos
    - Financial figures, equipment, contact details
    - "เซ้งได้แล้ว" (Transferred/Closed) status toggle: keeps listing on feed with prominent badge
    """
    import logging
    from decimal import Decimal, InvalidOperation
    from django.utils import timezone
    from apps.listings.models import Listing, ListingStatus, ListingType, generate_ref_code
    from apps.properties.models import PropertyType

    logger = logging.getLogger(__name__)

    property_obj = get_object_or_404(
        Property.objects.select_related('owner').prefetch_related('images', 'listings'),
        pk=pk
    )
    if not can_edit(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการแก้ไขข้อมูลทรัพย์สินนี้")

    listing = property_obj.listings.first()

    if request.method == 'POST':
        # 1. Update Property core fields
        title = request.POST.get('title', '').strip()
        prop_type = request.POST.get('type') or request.POST.get('category')
        desc = request.POST.get('desc', '').strip()
        province = request.POST.get('province', '').strip()
        district = request.POST.get('district', '').strip()
        address = request.POST.get('address', '').strip()
        postal = request.POST.get('postal', '20000').strip()
        google_maps_url = request.POST.get('google_maps_url', '').strip()

        try:
            area_sqm = Decimal(request.POST.get('area_sqm', '0') or '0')
        except (ValueError, InvalidOperation):
            area_sqm = property_obj.area_sqm

        try:
            floors = int(request.POST.get('floors', '1') or '1')
        except ValueError:
            floors = property_obj.floors

        if title:
            property_obj.title = title
        if prop_type:
            property_obj.type = prop_type
        if desc:
            property_obj.desc = desc
        if province:
            property_obj.province = province
        if district:
            property_obj.district = district
        if address:
            property_obj.address = address
        if postal:
            property_obj.postal = postal
        property_obj.google_maps_url = google_maps_url
        property_obj.area_sqm = area_sqm
        property_obj.floors = floors
        property_obj.save()

        # 2. Photos Management
        # Set cover image
        cover_image_id = request.POST.get('cover_image_id')
        if cover_image_id:
            property_obj.images.update(is_cover=False)
            property_obj.images.filter(pk=cover_image_id).update(is_cover=True)

        # Delete selected images
        delete_image_ids = request.POST.getlist('delete_image_ids')
        if delete_image_ids:
            property_obj.images.filter(pk__in=delete_image_ids).delete()

        # Upload new images
        new_images = request.FILES.getlist('images')
        if new_images:
            from apps.core.utils.files import validate_and_sanitize_image
            existing_count = property_obj.images.count()
            for idx, img_file in enumerate(new_images):
                try:
                    sanitized_file = validate_and_sanitize_image(img_file)
                    PropertyImage.objects.create(
                        property=property_obj,
                        image=sanitized_file,
                        is_cover=(existing_count == 0 and idx == 0),
                        order=existing_count + idx
                    )
                except Exception as e:
                    logger.warning(f"Failed to upload image {img_file.name}: {e}")

        # 3. Listing Fields Management
        try:
            raw_p = request.POST.get('price', '0').replace(',', '').strip()
            price = Decimal(raw_p) if raw_p else (listing.price if listing else Decimal('0.00'))
        except (ValueError, InvalidOperation):
            price = listing.price if listing else Decimal('0.00')

        try:
            raw_r = request.POST.get('monthly_rent', '0').replace(',', '').strip()
            monthly_rent = Decimal(raw_r) if raw_r else Decimal('0.00')
        except (ValueError, InvalidOperation):
            monthly_rent = Decimal('0.00')

        try:
            raw_d = request.POST.get('deposit_amount', '0').replace(',', '').strip()
            security_deposit = Decimal(raw_d) if raw_d else Decimal('0.00')
        except (ValueError, InvalidOperation):
            security_deposit = Decimal('0.00')

        try:
            lease_months = int(request.POST.get('remaining_lease_months', '0') or '0')
        except ValueError:
            lease_months = 0

        avg_profit = None
        profit_raw = request.POST.get('avg_profit_3m', '').replace(',', '').strip()
        if profit_raw:
            try:
                avg_profit = Decimal(profit_raw)
            except (ValueError, InvalidOperation):
                avg_profit = None

        avg_revenue = None
        rev_raw = request.POST.get('avg_revenue_3m', '').replace(',', '').strip()
        if rev_raw:
            try:
                avg_revenue = Decimal(rev_raw)
            except (ValueError, InvalidOperation):
                avg_revenue = None

        equipment = request.POST.get('equipment_included', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        contact_line_id = request.POST.get('contact_line_id', '').strip()
        is_closed = request.POST.get('is_closed') in ['1', 'true', 'on']
        includes_staff = request.POST.get('includes_staff') in ['1', 'true', 'on']
        is_admin_verified = request.POST.get('is_admin_verified') in ['1', 'true', 'on']

        lease_transfer_fee_raw = request.POST.get('lease_transfer_fee', '').replace(',', '').strip()
        try:
            lease_transfer_fee = Decimal(lease_transfer_fee_raw) if lease_transfer_fee_raw else Decimal('0.00')
        except (ValueError, InvalidOperation):
            lease_transfer_fee = Decimal('0.00')

        fee_payer = request.POST.get('lease_transfer_fee_payer', '').strip().lower()
        if fee_payer not in FeePayer.values:
            fee_payer = FeePayer.FREE

        if listing:
            listing.price = price
            listing.monthly_rent = monthly_rent
            listing.security_deposit = security_deposit
            listing.lease_remaining_months = lease_months
            listing.lease_transfer_fee = lease_transfer_fee
            listing.lease_transfer_fee_payer = fee_payer
            listing.includes_staff = includes_staff
            listing.avg_profit_3m = avg_profit
            listing.avg_revenue_3m = avg_revenue
            listing.includes_equipment = equipment
            if request.user.role in [UserRole.ADMIN, UserRole.STAFF]:
                listing.is_admin_verified = is_admin_verified
                if is_admin_verified and not listing.admin_verified_at:
                    listing.admin_verified_at = timezone.now()
                elif not is_admin_verified:
                    listing.admin_verified_at = None

            owner_name = request.POST.get('owner_name', '').strip()
            owner_facebook = request.POST.get('owner_facebook', '').strip()
            owner_notes = request.POST.get('owner_notes', '').strip()
            if owner_name:
                listing.owner_name = owner_name
            if contact_phone:
                listing.contact_phone = contact_phone
                if not listing.owner_phone:
                    listing.owner_phone = contact_phone
            if contact_line_id:
                listing.contact_line_id = contact_line_id
                if not listing.owner_line_id:
                    listing.owner_line_id = contact_line_id
            if owner_facebook:
                listing.owner_facebook = owner_facebook
            if owner_notes:
                listing.owner_notes = owner_notes

            # Status: "เซ้งได้แล้ว" Toggle Logic
            if is_closed:
                listing.status = ListingStatus.CLOSED
            elif listing.status == ListingStatus.CLOSED:
                listing.status = ListingStatus.PUBLISHED
            listing.save()
        elif price > 0:
            status = ListingStatus.CLOSED if is_closed else ListingStatus.PUBLISHED
            listing = Listing.objects.create(
                property=property_obj,
                ref_code=generate_ref_code(prefix='N' if request.user.is_staff_member() else 'F'),
                type=ListingType.TAKEOVER,
                price=price,
                monthly_rent=monthly_rent,
                security_deposit=security_deposit,
                lease_remaining_months=lease_months,
                avg_profit_3m=avg_profit,
                avg_revenue_3m=avg_revenue,
                includes_equipment=equipment,
                contact_phone=contact_phone,
                contact_line_id=contact_line_id,
                status=status,
                published_at=timezone.now()
            )

        AuditService.log(
            action='UPDATE',
            model_name='Property',
            object_id=property_obj.pk,
            changes={'title': property_obj.title, 'is_closed': is_closed},
            request=request
        )

        messages.success(request, f'✅ บันทึกข้อมูลและรูปภาพร้าน "{property_obj.title}" เรียบร้อยแล้ว!')
        if listing:
            return redirect('listings:listing_detail', pk=listing.pk)
        return redirect('properties:property_detail', pk=property_obj.pk)

    context = {
        'property': property_obj,
        'listing': listing,
        'images': property_obj.images.all(),
        'property_types': PropertyType.choices,
        'fee_payers': FeePayer.choices,
        'title': f'แก้ไขข้อมูลร้านค้า: {property_obj.title}',
    }
    return render(request, 'properties/property_form.html', context)


@login_required
@require_http_methods(["POST"])
def property_image_delete_view(request, pk, img_pk):
    """Delete a single property image via form action."""
    property_obj = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการแก้ไขรูปภาพนี้")

    image = get_object_or_404(PropertyImage, pk=img_pk, property=property_obj)
    image.delete()
    messages.success(request, 'ลบรูปภาพเรียบร้อยแล้ว')
    return redirect('properties:property_update', pk=property_obj.pk)


@login_required
@require_http_methods(["POST"])
def property_image_set_cover_view(request, pk, img_pk):
    """Set a specific image as the main cover photo."""
    property_obj = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการแก้ไขรูปภาพนี้")

    property_obj.images.update(is_cover=False)
    property_obj.images.filter(pk=img_pk).update(is_cover=True)
    messages.success(request, 'ตั้งเป็นภาพหน้าปกหลักเรียบร้อยแล้ว')
    return redirect('properties:property_update', pk=property_obj.pk)


@login_required
@require_http_methods(["POST"])
def property_delete_view(request, pk):
    """
    WHY SECURE:
    Enforces object-level can_delete check.
    Only the owner or admin/staff can delete.
    """
    property_obj = get_object_or_404(Property, pk=pk)
    if not can_delete(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการลบข้อมูลทรัพย์สินนี้")

    title = property_obj.title
    AuditService.log(
        action='DELETE',
        model_name='Property',
        object_id=property_obj.pk,
        changes={'title': title},
        request=request
    )
    property_obj.delete()
    messages.success(request, f'ลบข้อมูลทรัพย์สินร้านค้า "{title}" เรียบร้อยแล้ว')
    return redirect('properties:property_list')
