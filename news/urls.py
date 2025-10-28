from django.urls import path
from . import views

urlpatterns = [
    # News endpoints
    path('fetch/', views.fetch_and_store_news, name='fetch_news'),
    path('articles/', views.get_news_articles, name='get_news_articles'),
    path('latest/', views.get_latest_news, name='get_latest_news'),
    
    # Alert endpoints
    path('alerts/unsent/', views.get_unsent_alerts, name='get_unsent_alerts'),
    path('alerts/accepted-unsent/', views.get_and_mark_accepted_alerts, name='get_and_mark_accepted_alerts'),
    path('alerts/<int:alert_id>/status/', views.update_alert_status, name='update_alert_status'),
    path('alerts/process-and-call-decision-api/', views.process_news_alerts_and_call_decision_api, name='process_news_alerts_and_call_decision_api'),
]
