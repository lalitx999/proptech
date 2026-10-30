from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),

    # WHY SEO CRITICAL: /packages/, /pricing/ and /accounts/vip/ all rendered the same
    # VIP pricing template — three URLs for one document is classic duplicate content.
    # /accounts/vip/ is now the single canonical URL (used by sitemap.xml & llms.txt) and
    # the legacy aliases issue HTTP 301 so any backlinks or ads keep passing PageRank.
    path('packages/', RedirectView.as_view(pattern_name='accounts:vip_membership', permanent=True), name='packages'),
    path('pricing/', RedirectView.as_view(pattern_name='accounts:vip_membership', permanent=True), name='pricing'),

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
