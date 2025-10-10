from django.urls import path
from . import views

urlpatterns = [
    path('fetch/', views.fetch_and_store_news, name='fetch_news'),
    path('articles/', views.get_news_articles, name='get_news_articles'),
    path('latest/', views.get_latest_news, name='get_latest_news'),
]
