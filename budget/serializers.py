from rest_framework import serializers
from .models import Projects, ProjectCosts, ProjectOverheads, ProjectCostVersion, ProjectOverheadVersion, ProjectVersion


class ProjectsSerializer(serializers.ModelSerializer):
    """
    Serializer for Projects model.
    Handles validation and serialization of project data.
    """
    
    class Meta:
        model = Projects
        fields = [
            'id',
            'name',
            'location',
            'start_date',
            'end_date',
            'total_project_cost',
            'version_number',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'version_number', 'created_at', 'updated_at']

    def validate_name(self, value):
        """Validate that project name is not empty"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Project name cannot be empty")
        return value.strip()

    def validate(self, data):
        """Validate that end_date is after start_date"""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError("End date must be after start date")
        
        return data


class ProjectCostsSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectCosts model.
    Handles validation and serialization of project cost data.
    """
    
    class Meta:
        model = ProjectCosts
        fields = [
            'id',
            'project',
            'category_code',
            'category_name',
            'item_description',
            'supplier_brand',
            'unit',
            'quantity',
            'rate_per_unit',
            'line_total',
            'category_total',
            'version_number',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'line_total', 'version_number', 'created_at', 'updated_at']

    def validate_quantity(self, value):
        """Validate that quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

    def validate_rate_per_unit(self, value):
        """Validate that rate per unit is positive"""
        if value <= 0:
            raise serializers.ValidationError("Rate per unit must be greater than 0")
        return value

    def validate_category_code(self, value):
        """Validate category code format"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Category code cannot be empty")
        return value.upper()  # Convert to uppercase for consistency


class ProjectOverheadsSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectOverheads model.
    Handles validation and serialization of project overhead data.
    """
    
    class Meta:
        model = ProjectOverheads
        fields = [
            'id',
            'project',
            'overhead_type',
            'description',
            'basis',
            'percentage',
            'amount',
            'version_number',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'version_number', 'created_at', 'updated_at']

    def validate_percentage(self, value):
        """Validate that percentage is between 0 and 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("Percentage must be between 0 and 100")
        return value

    def validate_amount(self, value):
        """Validate that amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value

    def validate_overhead_type(self, value):
        """Validate overhead type format"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Overhead type cannot be empty")
        return value.title()  # Convert to title case for consistency


class ProjectCostVersionSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectCostVersion model.
    Handles serialization of project cost version history.
    """
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = ProjectCostVersion
        fields = [
            'id',
            'original_record',
            'project',
            'category_code',
            'category_name',
            'item_description',
            'supplier_brand',
            'unit',
            'quantity',
            'rate_per_unit',
            'line_total',
            'category_total',
            'version_number',
            'changed_by',
            'changed_by_username',
            'change_reason',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ProjectOverheadVersionSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectOverheadVersion model.
    Handles serialization of project overhead version history.
    """
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = ProjectOverheadVersion
        fields = [
            'id',
            'original_record',
            'project',
            'overhead_type',
            'description',
            'basis',
            'percentage',
            'amount',
            'version_number',
            'changed_by',
            'changed_by_username',
            'change_reason',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ProjectLatestDataSerializer(serializers.ModelSerializer):
    """
    Serializer for complete project data with latest versions.
    """
    project_costs = ProjectCostsSerializer(source='projectcosts_set', many=True, read_only=True)
    project_overheads = ProjectOverheadsSerializer(source='projectoverheads_set', many=True, read_only=True)
    total_cost = serializers.SerializerMethodField()
    total_overhead = serializers.SerializerMethodField()
    
    class Meta:
        model = Projects
        fields = [
            'id',
            'name',
            'location',
            'start_date',
            'end_date',
            'project_costs',
            'project_overheads',
            'total_cost',
            'total_overhead',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_cost(self, obj):
        """Calculate total cost from all project costs"""
        return sum(cost.line_total for cost in obj.projectcosts_set.all())
    
    def get_total_overhead(self, obj):
        """Calculate total overhead from all project overheads"""
        return sum(overhead.amount for overhead in obj.projectoverheads_set.all())


class ProjectVersionSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectVersion model.
    Handles serialization of project version history.
    """
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = ProjectVersion
        fields = [
            'id',
            'original_record',
            'name',
            'location',
            'start_date',
            'end_date',
            'total_project_cost',
            'version_number',
            'changed_by',
            'changed_by_username',
            'change_reason',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
