from django.urls import path
from . import views

app_name = 'listings'

urlpatterns = [
    path('', views.marketplace_view, name='marketplace'),
    path('manage/', views.listing_list_view, name='listing_list'),
    path('create/', views.consignment_wizard_view, name='listing_create'),
    path('create/<int:property_pk>/', views.listing_create_view, name='listing_create'),
    path('create/<int:property_pk>/', views.listing_create_view, name='listing_create_property'),
    path('compare/', views.listing_compare_view, name='listing_compare'),
    path('favorites/', views.listing_favorites_view, name='listing_favorites'),
    path('<int:pk>/', views.listing_detail_view, name='listing_detail'),
    path('<int:pk>/approve/', views.listing_approval_view, name='listing_approval'),
]
