from django.urls import path
from . import views

urlpatterns = [
    # Authentication endpoints
    path('register/', views.user_detail_register_view, name='register'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('login/', views.user_detail_login_view, name='login'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('logout/', views.logout_view, name='logout'),
]
