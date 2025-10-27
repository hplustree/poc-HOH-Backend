from rest_framework import serializers
from .models import Session, Conversation, Messages, UpdatedCost
from budget.models import Projects
from authentication.models import UserDetail


class SessionSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project_id.name', read_only=True)
    user_email = serializers.CharField(source='user_id.email', read_only=True)
    
    class Meta:
        model = Session
        fields = ['session_id', 'project_id', 'user_id', 'project_name', 'user_email', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['session_id', 'created_at', 'updated_at']


class ConversationSerializer(serializers.ModelSerializer):
    session_id = serializers.IntegerField(source='session.session_id', read_only=True)
    project_name = serializers.CharField(source='project_id.name', read_only=True)
    user_email = serializers.CharField(source='session.user_id.email', read_only=True)
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['conversation_id', 'session_id', 'project_id', 'project_name', 'user_email', 'message_count']
        read_only_fields = ['conversation_id']
    
    def get_message_count(self, obj):
        return obj.messages.count()

class ConversationCreateSerializer(serializers.ModelSerializer):
    session_id = serializers.IntegerField()
    project_id = serializers.IntegerField(required=True)
    
    class Meta:
        model = Conversation
        fields = ['session_id', 'project_id']
    
    def validate_session_id(self, value):
        try:
            session = Session.objects.get(session_id=value, is_active=True)
            return value
        except Session.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive session ID")
    
    def validate_project_id(self, value):
        try:
            project = Projects.objects.get(id=value)
            return value
        except Projects.DoesNotExist:
            raise serializers.ValidationError("Invalid project ID")
    
    def create(self, validated_data):
        session_id = validated_data['session_id']
        project_id = validated_data['project_id']
        session = Session.objects.get(session_id=session_id)
        project = Projects.objects.get(id=project_id)
        return Conversation.objects.create(session=session, project_id=project)


class MessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.CharField(source='sender.email', read_only=True)
    
    class Meta:
        model = Messages
        fields = ['message_id', 'conversation', 'sender', 'sender_email', 'message_type', 'content', 'metadata', 'is_hide', 'created_at', 'updated_at']
        read_only_fields = ['message_id', 'created_at', 'updated_at']


class MessageCreateSerializer(serializers.Serializer):
    """Serializer for creating a new message and sending to external API"""
    session_id = serializers.IntegerField()
    conversation_id = serializers.IntegerField(required=False)
    content = serializers.CharField()
    message_type = serializers.ChoiceField(choices=Messages.MESSAGE_TYPES, default='user')
    
    def validate_session_id(self, value):
        try:
            session = Session.objects.get(session_id=value, is_active=True)
            return value
        except Session.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive session ID")


class ChatHistorySerializer(serializers.Serializer):
    """Serializer for formatting chat history for external API"""
    Human = serializers.CharField()
    AI = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class UpdatedCostSerializer(serializers.ModelSerializer):
    """Serializer for UpdatedCost model"""
    conversation_id = serializers.IntegerField(source='conversation.conversation_id', read_only=True)
    message_id = serializers.IntegerField(source='message.message_id', read_only=True)
    
    class Meta:
        model = UpdatedCost
        fields = [
            'updated_cost_id', 'conversation_id', 'message_id', 'project_name', 
            'project_location', 'total_cost', 'start_date', 'end_date',
            'cost_line_items', 'overheads', 'is_accept', 'accepted_at',
            'raw_costing_response', 'created_at', 'updated_at'
        ]
        read_only_fields = ['updated_cost_id', 'created_at', 'updated_at']


class UpdatedCostStatusSerializer(serializers.ModelSerializer):
    """Serializer for updating UpdatedCost acceptance status"""
    
    class Meta:
        model = UpdatedCost
        fields = ['is_accept']
    
    def update(self, instance, validated_data):
        """Override update to handle accepted_at timestamp"""
        if validated_data.get('is_accept') is True:
            from django.utils import timezone
            instance.accepted_at = timezone.now()
        elif validated_data.get('is_accept') is False:
            instance.accepted_at = None
            
        instance.is_accept = validated_data.get('is_accept')
        instance.save()
        return instance
