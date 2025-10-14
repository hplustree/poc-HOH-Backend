from rest_framework import serializers
from .models import Projects, ProjectCosts, ProjectOverheads

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
        fields = ['id', 'name', 'location', 'start_date', 'end_date', 'version_number', 'created_at', 'updated_at', 'costs', 'overheads']
        read_only_fields = ('version_number', 'created_at', 'updated_at')

class PDFExtractionSerializer(serializers.Serializer):
    project = serializers.DictField()
    cost_line_items = serializers.ListField(child=serializers.DictField())
    overheads = serializers.ListField(child=serializers.DictField(), required=False)
    
    def create(self, validated_data):
        # This will be handled in the view
        return validated_data
