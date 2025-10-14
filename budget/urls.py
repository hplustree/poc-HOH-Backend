from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import PDFExtractionView

app_name = 'budget'

urlpatterns = [
    # PDF extraction endpoint
    path('api/extract-pdf/', PDFExtractionView.as_view(), name='extract-pdf'),
]
