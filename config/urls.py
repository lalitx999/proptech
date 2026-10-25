from django.conf import settings
from django.urls import path, include

from apps.accounts import admin_views

urlpatterns = [
    path('', include('apps.core.urls')),
    path('admin-dashboard/', include([
        path('', admin_views.admin_command_center_view, name='admin_dashboard_root'),
        path('shops/<int:pk>/update-owner/', admin_views.admin_update_shop_owner_view, name='admin_update_shop_owner_root'),
        path('shops/<int:pk>/delete-owner/', admin_views.admin_delete_shop_owner_view, name='admin_delete_shop_owner_root'),
        path('shops/<int:pk>/action/', admin_views.admin_shop_action_view, name='admin_shop_action_root'),
        path('shops/fast-create/', admin_views.admin_fast_create_shop_view, name='admin_fast_create_shop_root'),
        path('leads/<int:pk>/action/', admin_views.admin_lead_action_view, name='admin_lead_action_root'),
        path('deals/<int:pk>/action/', admin_views.admin_deal_action_view, name='admin_deal_action_root'),
        path('agents/create/', admin_views.admin_create_agent_view, name='admin_create_agent_root'),
        path('agents/<int:pk>/action/', admin_views.admin_agent_action_view, name='admin_agent_action_root'),
        path('telegram/detect/', admin_views.admin_telegram_detect_view, name='admin_telegram_detect_root'),
        path('messages/<int:pk>/resolve/', admin_views.admin_resolve_message_view, name='admin_resolve_message_root'),
    ])),
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
