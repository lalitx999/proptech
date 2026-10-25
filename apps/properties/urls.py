from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    path('', views.property_list_view, name='property_list'),
    path('create/', views.property_create_view, name='property_create'),
    path('<int:pk>/', views.property_detail_view, name='property_detail'),
    path('<int:pk>/edit/', views.property_update_view, name='property_update'),
    path('<int:pk>/delete/', views.property_delete_view, name='property_delete'),
    path('<int:pk>/images/<int:img_pk>/delete/', views.property_image_delete_view, name='property_image_delete'),
    path('<int:pk>/images/<int:img_pk>/cover/', views.property_image_set_cover_view, name='property_image_set_cover'),
]
