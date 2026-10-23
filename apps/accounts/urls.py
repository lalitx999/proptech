from django.urls import path
from . import views
from . import admin_views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email_view, name='verify_email'),
    path('login/', views.login_view, name='login'),
    path('2fa/verify/', views.two_factor_verify_view, name='two_factor_verify'),
    path('logout/', views.logout_view, name='logout'),
    path('vip/', views.vip_membership_view, name='vip_membership'),
    path('vip/manage/', views.vip_manage_view, name='vip_manage'),
    path('vip/approve/<int:pk>/', views.vip_approve_transaction_view, name='vip_approve'),
    
    # Custom Admin Command Center (Unified Dashboard)
    path('dashboard/', admin_views.admin_command_center_view, name='admin_dashboard'),
    path('dashboard/shops/<int:pk>/action/', admin_views.admin_shop_action_view, name='admin_shop_action'),
    path('dashboard/shops/fast-create/', admin_views.admin_fast_create_shop_view, name='admin_fast_create_shop'),
    path('dashboard/leads/<int:pk>/action/', admin_views.admin_lead_action_view, name='admin_lead_action'),
    path('dashboard/deals/<int:pk>/action/', admin_views.admin_deal_action_view, name='admin_deal_action'),
    path('dashboard/messages/<int:pk>/resolve/', admin_views.admin_resolve_message_view, name='admin_resolve_message'),
    path('dashboard/telegram/detect/', admin_views.admin_telegram_detect_view, name='admin_telegram_detect'),
]

