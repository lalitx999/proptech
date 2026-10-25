from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    path('', views.property_list_view, name='property_list'),
    path('create/', views.property_create_view, name='property_create'),
    path('<int:pk>/', views.property_detail_view, name='property_detail'),
    path('<int:pk>/edit/', views.property_update_view, name='property_update'),
    path('<int:pk>/delete/', views.property_delete_view, name='property_delete'),
]
