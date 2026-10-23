from functools import wraps
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.contrib.auth.mixins import AccessMixin
from apps.accounts.models import UserRole
from apps.accounts.services.audit import AuditService

def role_required(*allowed_roles):
    """
    WHY SECURE: Function decorator enforcing role-based access control.
    1. Authenticates identity.
    2. Verifies user role strictly against whitelist.
    3. Records PERMISSION_DENIED to AuditLog on unauthorized attempt.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            AuditService.log(
                action='PERMISSION_DENIED',
                model_name='Endpoint',
                object_id=request.path,
                changes={
                    'user_role': request.user.role,
                    'required_roles': list(allowed_roles),
                },
                request=request
            )
            raise PermissionDenied("คุณไม่มีสิทธิ์ในการเข้าถึงส่วนงานนี้")
        return _wrapped_view
    return decorator

class RoleRequiredMixin(AccessMixin):
    """CBV Mixin for role-based access control."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser or request.user.role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)

        AuditService.log(
            action='PERMISSION_DENIED',
            model_name=self.__class__.__name__,
            object_id=request.path,
            changes={
                'user_role': request.user.role,
                'required_roles': list(self.allowed_roles),
            },
            request=request
        )
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการเข้าถึงส่วนงานนี้")

# ==============================================================================
# ROW-LEVEL AUTHORIZATION HELPERS
# ==============================================================================

def get_scoped_queryset(user, queryset, owner_field=None, agent_field='agent', status_field='status'):
    """
    WHY SECURE: Row-level queryset scoping to prevent Insecure Direct Object References (IDOR).
    Automatically resolves whether ownership is direct (Property.owner)
    or nested (Listing.property.owner).
    """
    model_name = queryset.model._meta.model_name
    if owner_field is None:
        owner_field = 'property__owner' if model_name == 'listing' else 'owner'

    if not user.is_authenticated:
        if hasattr(queryset.model, status_field):
            return queryset.filter(**{status_field: 'published'})
        return queryset.none()

    if user.is_admin() or user.is_staff_member():
        return queryset.all()

    if user.role == UserRole.AGENT:
        filters = Q(**{owner_field: user})
        if hasattr(queryset.model, agent_field):
            filters |= Q(**{agent_field: user})
        return queryset.filter(filters)

    if user.role == UserRole.CUSTOMER:
        if hasattr(queryset.model, status_field):
            return queryset.filter(Q(**{owner_field: user}) | Q(**{status_field: 'published'}))
        return queryset.filter(**{owner_field: user})

    # For Owners and other authenticated roles: filter by their own records
    return queryset.filter(**{owner_field: user})

# ==============================================================================
# OBJECT-LEVEL AUTHORIZATION RULES
# ==============================================================================

def _get_object_owner(obj):
    """Extract owner whether object is Property, Listing, or Contract."""
    if hasattr(obj, 'owner'):
        return obj.owner
    if hasattr(obj, 'property') and hasattr(obj.property, 'owner'):
        return obj.property.owner
    return None

def _get_object_agent(obj):
    """Extract assigned agent."""
    if hasattr(obj, 'agent'):
        return obj.agent
    if hasattr(obj, 'assigned_agent'):
        return obj.assigned_agent
    return None

def can_view(user, obj):
    """Object-level view permission check."""
    status = getattr(obj, 'status', None)
    if status in ['published', 'active']:
        return True
    if not user.is_authenticated:
        return False
    if user.is_admin() or user.is_staff_member():
        return True
    owner = _get_object_owner(obj)
    if owner and owner == user:
        return True
    agent = _get_object_agent(obj)
    if agent and agent == user:
        return True
    return False

def can_edit(user, obj):
    """Object-level edit permission check."""
    if not user.is_authenticated:
        return False
    if user.is_admin() or user.is_staff_member():
        return True
    status = getattr(obj, 'status', 'draft')
    owner = _get_object_owner(obj)
    if owner and owner == user:
        return status in ['draft', 'pending']
    agent = _get_object_agent(obj)
    if agent and agent == user:
        return status in ['draft', 'pending']
    return False

def can_delete(user, obj):
    """Object-level delete permission check."""
    if not user.is_authenticated:
        return False
    if user.is_admin():
        return True
    status = getattr(obj, 'status', 'draft')
    owner = _get_object_owner(obj)
    if owner and owner == user:
        return status == 'draft'
    return False
