from rest_framework import serializers
from .models import Projects, ProjectCosts, ProjectOverheads
from chatapp.models import Messages

class ProjectCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCosts
        fields = '__all__'
        read_only_fields = ('version_number', 'created_at', 'updated_at')

class ProjectOverheadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectOverheads
        fields = '__all__'
        read_only_fields = ('version_number', 'created_at', 'updated_at')

class ProjectSerializer(serializers.ModelSerializer):
    costs = ProjectCostSerializer(many=True, required=False)
    overheads = ProjectOverheadSerializer(many=True, required=False)
    
    class Meta:
        model = Projects
        fields = ['id', 'name', 'location', 'start_date', 'end_date', 'total_cost', 'version_number', 'created_at', 'updated_at', 'costs', 'overheads']
        read_only_fields = ('version_number', 'created_at', 'updated_at')

class PDFExtractionSerializer(serializers.Serializer):
    project = serializers.DictField()
    cost_line_items = serializers.ListField(child=serializers.DictField())
    overheads = serializers.ListField(child=serializers.DictField(), required=False)
    
    def create(self, validated_data):
        # This will be handled in the view
        return validated_data


class ChatAcceptRequestSerializer(serializers.Serializer):
    """Serializer for chat-accept request with message_id and approval"""
    message_id = serializers.IntegerField()
    approval = serializers.ChoiceField(choices=['accept', 'reject'])
    
    def validate_message_id(self, value):
        """Validate that message exists and has metadata with costing data"""
        try:
            message = Messages.objects.get(message_id=value)
            if not message.metadata:
                raise serializers.ValidationError("Message does not contain metadata")
            
            # Check for costing data in chatbot_response.costing
            chatbot_response = message.metadata.get('chatbot_response', {})
            if not chatbot_response.get('costing'):
                raise serializers.ValidationError("Message does not contain costing data in chatbot_response")
            
            return value
        except Messages.DoesNotExist:
            raise serializers.ValidationError("Message with this ID does not exist")


class ChatAcceptResponseSerializer(serializers.Serializer):
    """Serializer for chat-accept API response"""
    status = serializers.CharField()
    answer = serializers.CharField()
    costing_json = serializers.DictField()
    
    def validate_status(self, value):
        if value != 'success':
            raise serializers.ValidationError("API response status is not success")
        return value


class CostingJsonSerializer(serializers.Serializer):
    """Serializer for costing_json data structure"""
    project = serializers.DictField()
    cost_line_items = serializers.ListField(child=serializers.DictField())
    overheads = serializers.ListField(child=serializers.DictField())


class LatestCostingResponseSerializer(serializers.Serializer):
    """Serializer for latest costing API response"""
    costing_json = CostingJsonSerializer()
