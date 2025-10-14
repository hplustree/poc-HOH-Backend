from django.contrib import admin
from .models import Session, Conversation, Messages


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'project_id', 'user_id', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at', 'project_id']
    search_fields = ['project_id__name', 'user_id__email']
    readonly_fields = ['session_id', 'created_at', 'updated_at']
    ordering = ['-updated_at']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['conversation_id', 'session']
    list_filter = ['session__project_id']
    search_fields = ['session__project_id__name']
    readonly_fields = ['conversation_id']
    ordering = ['-conversation_id']


@admin.register(Messages)
class MessagesAdmin(admin.ModelAdmin):
    list_display = ['message_id', 'conversation', 'sender', 'message_type', 'content_preview', 'created_at']
    list_filter = ['message_type', 'created_at', 'conversation__session__project_id']
    search_fields = ['content', 'sender__email']
    readonly_fields = ['message_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def content_preview(self, obj):
        """Show first 50 characters of message content"""
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content Preview'
