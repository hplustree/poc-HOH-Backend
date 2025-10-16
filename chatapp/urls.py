from django.urls import path
from . import views

urlpatterns = [
    # Session management (using class-based view for both list and create)
    path('sessions/', views.SessionListCreateView.as_view(), name='session-list-create'),
    
    # Conversation management
    path('conversations/', views.get_all_conversations, name='get_all_conversations'),
    path('conversations/create/', views.create_conversation, name='create_conversation'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
    
    # Message handling
    path('messages/send/', views.send_message, name='send_message'),
    path('conversations/<int:conversation_id>/history/', views.get_conversation_history, name='get_conversation_history'),
    path('chats/', views.get_all_chats, name='get_all_chats'),
    
    # Updated costs management
    path('updated-costs/', views.get_updated_costs, name='get_updated_costs'),
    path('updated-costs/<int:updated_cost_id>/', views.get_updated_cost_detail, name='get_updated_cost_detail'),
    path('updated-costs/<int:updated_cost_id>/status/', views.update_cost_status, name='update_cost_status'),
]
