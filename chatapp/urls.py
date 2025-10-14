from django.urls import path
from . import views

urlpatterns = [
    # Session management
    path('sessions/create/', views.create_session, name='create_chat_session'),
    path('sessions/', views.get_user_sessions, name='get_user_sessions'),
    
    # Message handling
    path('messages/send/', views.send_message, name='send_message'),
    path('conversations/<int:conversation_id>/history/', views.get_conversation_history, name='get_conversation_history'),
    
    # Updated costs management
    path('updated-costs/', views.get_updated_costs, name='get_updated_costs'),
    path('updated-costs/<int:updated_cost_id>/', views.get_updated_cost_detail, name='get_updated_cost_detail'),
    path('updated-costs/<int:updated_cost_id>/status/', views.update_cost_status, name='update_cost_status'),
]
