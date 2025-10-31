from django.db import models
from django.utils import timezone
from budget.models import Projects
from authentication.models import UserDetail


class Session(models.Model):
    """Chat session linked to a specific project"""
    session_id = models.AutoField(primary_key=True)
    project_id = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='chat_sessions')
    user_id = models.ForeignKey(UserDetail, on_delete=models.CASCADE, related_name='chat_sessions')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-updated_at']
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'
    
    def __str__(self):
        return f"Session {self.session_id} - {self.project_id.name} ({self.user_id.email})"


class Conversation(models.Model):
    """Individual conversation within a session"""
    conversation_id = models.AutoField(primary_key=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='conversations')
    project_id = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='conversations')
    
    class Meta:
        db_table = 'conversations'
        ordering = ['-conversation_id']
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
    
    def __str__(self):
        return f"Conversation {self.conversation_id} - {self.project_id.name}"


class Messages(models.Model):
    """Individual messages within a conversation"""
    MESSAGE_TYPES = [
        ('user', 'User Message'),
        ('assistant', 'Assistant Message'),
        ('system', 'System Message'),
    ]
    
    message_id = models.AutoField(primary_key=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='session_messages', null=True, blank=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(UserDetail, on_delete=models.CASCADE, related_name='sent_messages', null=True, blank=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='user')
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_hide = models.BooleanField(default=False)
    is_accept = models.BooleanField(default=False, null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
    
    def __str__(self):
        return f"Message {self.message_id} - {self.message_type}"
    
    def accept_message(self):
        """Mark message as accepted"""
        self.is_accept = True
        self.accepted_at = timezone.now()
        self.save()


class UpdatedCost(models.Model):
    """Store updated costing data from chatbot responses"""
    updated_cost_id = models.AutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='updated_costs')
    message = models.ForeignKey(Messages, on_delete=models.CASCADE, related_name='updated_costs', null=True, blank=True)
    
    # Project information
    project_name = models.CharField(max_length=255)
    project_location = models.CharField(max_length=500, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Cost line items (stored as JSON)
    cost_line_items = models.JSONField(default=list)
    
    # Overheads (stored as JSON)
    overheads = models.JSONField(default=list)
    
    # Status and metadata
    is_accept = models.BooleanField(default=False, null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    # Raw response data for reference
    raw_costing_response = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'updated_costs'
        ordering = ['-created_at']
        verbose_name = 'Updated Cost'
        verbose_name_plural = 'Updated Costs'
    
    def __str__(self):
        return f"Updated Cost {self.updated_cost_id} - {self.project_name}"
    
    def accept_cost_update(self):
        """Mark cost update as accepted"""
        self.is_accept = True
        self.accepted_at = timezone.now()
        self.save()
