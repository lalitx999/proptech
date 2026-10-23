from django.urls import path
from . import views

app_name = 'contracts'

urlpatterns = [
    path('pipeline/', views.deal_pipeline_view, name='deal_pipeline'),
    path('deals/<int:pk>/', views.deal_detail_view, name='deal_detail'),
    path('deals/<int:pk>/stage/', views.deal_advance_stage_view, name='deal_advance_stage'),
    path('deals/<int:pk>/upload-document/', views.deal_upload_document_view, name='deal_upload_document'),
    path('documents/<int:pk>/download/', views.contract_document_download_view, name='document_download'),
]
