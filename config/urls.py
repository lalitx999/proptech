from django.conf import settings
from django.urls import path, include

from apps.accounts.admin_views import admin_command_center_view

urlpatterns = [
    path('', include('apps.core.urls')),
    path('admin-dashboard/', admin_command_center_view, name='admin_dashboard_root'),
    path('accounts/', include('apps.accounts.urls')),
    path('properties/', include('apps.properties.urls')),
    path('listings/', include('apps.listings.urls')),
    path('leads/', include('apps.leads.urls')),
    path('contracts/', include('apps.contracts.urls')),
]

# ==============================================================================
# CONDITIONAL ADMIN (FORBIDDEN ON PRODUCTION)
# ==============================================================================
# WHY SECURE: Non-negotiable requirement specifies NO Django Admin on production.
# The endpoint is completely omitted from the URL routing table in prod.
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if 'django.contrib.admin' in settings.INSTALLED_APPS:
        from django.contrib import admin
        urlpatterns.append(path('dev-admin-only/', admin.site.urls))

# Custom Error Handlers (Prevents stack trace leaks to end-users)
handler403 = 'apps.core.views.permission_denied_view'
handler404 = 'apps.core.views.not_found_view'
handler500 = 'apps.core.views.server_error_view'
