from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('inquiry/<int:listing_pk>/', views.submit_inquiry_view, name='submit_inquiry'),
]
