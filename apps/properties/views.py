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
    """
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
@require_http_methods(["GET", "POST"])
def property_update_view(request, pk):
    """
    WHY SECURE:
    Enforces object-level can_edit check.
    """
    property_obj = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, property_obj):
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการแก้ไขข้อมูลทรัพย์สินนี้")

    if request.method == 'POST':
        form = PropertyForm(request.POST, instance=property_obj)
        if form.is_valid():
            property_obj = form.save()
            AuditService.log(
                action='UPDATE',
                model_name='Property',
                object_id=property_obj.pk,
                changes={'title': property_obj.title},
                request=request
            )
            messages.success(request, 'บันทึกการแก้ไขเรียบร้อยแล้ว')
            return redirect('properties:property_detail', pk=property_obj.pk)
    else:
        form = PropertyForm(instance=property_obj)

    return render(request, 'properties/property_form.html', {'form': form, 'title': 'แก้ไขข้อมูลทรัพย์สิน'})
