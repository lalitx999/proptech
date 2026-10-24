from django.urls import path
from . import views
from apps.accounts import views as accounts_views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('packages/', accounts_views.vip_membership_view, name='packages'),
    path('pricing/', accounts_views.vip_membership_view, name='pricing'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_view, name='contact'),
    path('privacy-policy/', views.privacy_policy_view, name='privacy_policy'),
    path('terms-of-service/', views.terms_of_service_view, name='terms_of_service'),
    path('robots.txt', views.robots_txt_view, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml_view, name='sitemap_xml'),
    path('llms.txt', views.llms_txt_view, name='llms_txt'),
    path('llms-full.txt', views.llms_full_txt_view, name='llms_full_txt'),
    path('healthz', views.healthz_view, name='healthz'),
    path('healthz/', views.healthz_view, name='healthz_slash'),
    path('manifest.json', views.manifest_json_view, name='manifest_json'),
    path('sw.js', views.service_worker_view, name='service_worker'),
]
