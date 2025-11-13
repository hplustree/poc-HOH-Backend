from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import PDFExtractionView, ChatAcceptView, LatestCostingView, ProjectVersionHistoryView, ProjectListView

app_name = 'budget'

urlpatterns = [
    # PDF extraction endpoint
    path('extract-pdf/', PDFExtractionView.as_view(), name='extract-pdf'),
    # Chat accept endpoint
    path('chat-accept/', ChatAcceptView.as_view(), name='chat-accept'),
    # Latest costing data endpoints
    path('api/latest-costing/', LatestCostingView.as_view(), name='latest-costing'),
    path('api/latest-costing/<int:project_id>/', LatestCostingView.as_view(), name='latest-costing-by-id'),
    # Project version history endpoint
    path('projects/<int:project_id>/version-history/', ProjectVersionHistoryView.as_view(), name='project-version-history'),
    # Projects list endpoint
    path('projects/', ProjectListView.as_view(), name='project-list'),
]
