from rest_framework import serializers
from .models import Projects, ProjectCosts, ProjectOverheads, ProjectVersion, ProjectCostVersion, ProjectOverheadVersion
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
    project_id = serializers.CharField(required=False, allow_null=True)
    version_id = serializers.CharField(required=False, allow_null=True)
    
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
    final_action = serializers.ChoiceField(choices=['accept', 'reject'])
    
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


class ProjectVersionCostSerializer(serializers.ModelSerializer):
    """Serializer for project costs in version history"""
    class Meta:
        model = ProjectCosts
        fields = ['id', 'category_code', 'category_name', 'item_description', 'supplier_brand', 
                 'unit', 'quantity', 'rate_per_unit', 'line_total', 'category_total']


class ProjectVersionOverheadSerializer(serializers.ModelSerializer):
    """Serializer for project overheads in version history"""
    class Meta:
        model = ProjectOverheads
        fields = ['id', 'overhead_type', 'description', 'basis', 'percentage', 'amount']


class ProjectVersionHistorySerializer(serializers.Serializer):
    """Serializer for each project version with its costs and overheads"""
    version_number = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)
    timestamp = serializers.DateTimeField()
    change_reason = serializers.CharField(allow_null=True, allow_blank=True)
    changed_by = serializers.CharField()
    project_costs = ProjectVersionCostSerializer(many=True)
    project_overheads = ProjectVersionOverheadSerializer(many=True)


class ProjectDetailSerializer(serializers.ModelSerializer):
    """Serializer for basic project details"""
    current_version = serializers.IntegerField(source='version_number')
    
    class Meta:
        model = Projects
        fields = ['id', 'name', 'location', 'start_date', 'end_date', 'current_version', 'created_at', 'updated_at']


class ProjectVersionHistoryResponseSerializer(serializers.Serializer):
    """Complete response serializer for project version history API"""
    status = serializers.CharField()
    message = serializers.CharField()
    project_detail = ProjectDetailSerializer()
    project_versions = ProjectVersionHistorySerializer(many=True)
