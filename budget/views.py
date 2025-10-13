from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Projects, ProjectCosts, ProjectOverheads, ProjectCostVersion, ProjectOverheadVersion, ProjectVersion
from .serializers import (
    ProjectsSerializer, ProjectCostsSerializer, ProjectOverheadsSerializer,
    ProjectCostVersionSerializer, ProjectOverheadVersionSerializer, ProjectLatestDataSerializer, ProjectVersionSerializer
)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    """
    Create a new project.
    
    POST /api/budget/projects/
    
    Expected payload:
    {
        "name": "Corporate Building Project",
        "location": "New York, NY",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
    }
    """
    try:
        serializer = ProjectsSerializer(data=request.data)
        
        if serializer.is_valid():
            project = serializer.save()
            
            # Return the created object
            response_serializer = ProjectsSerializer(project)
            
            return Response({
                'success': True,
                'message': 'Project created successfully',
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_projects(request):
    """
    List all projects with optional filtering.
    
    GET /api/budget/projects/
    
    Query parameters:
    - name: Filter by project name
    - location: Filter by location
    """
    try:
        queryset = Projects.objects.all()
        
        # Apply filters if provided
        name = request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
            
        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        serializer = ProjectsSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'count': queryset.count(),
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_cost(request):
    """
    Create a new project cost entry.
    
    POST /api/budget/project-costs/
    
    Expected payload:
    {
        "project": 1,
        "category_code": "A",
        "category_name": "Civil & Structural Works",
        "item_description": "Site preparation & excavation",
        "supplier_brand": "BuildSmart Contractors",
        "unit": "Lump sum",
        "quantity": 1.00,
        "rate_per_unit": 40000000.00,
        "category_total": 40000000.00
    }
    """
    try:
        serializer = ProjectCostsSerializer(data=request.data)
        
        if serializer.is_valid():
            project_cost = serializer.save()
            
            # Return the created object with calculated line_total
            response_serializer = ProjectCostsSerializer(project_cost)
            
            return Response({
                'success': True,
                'message': 'Project cost created successfully',
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_project_costs(request):
    """
    List all project costs with optional filtering.
    
    GET /api/budget/project-costs/
    
    Query parameters:
    - project_id: Filter by project ID
    - category_code: Filter by category code
    """
    try:
        queryset = ProjectCosts.objects.all()
        
        # Apply filters if provided
        project_id = request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
            
        category_code = request.query_params.get('category_code')
        if category_code:
            queryset = queryset.filter(category_code__iexact=category_code)
        
        serializer = ProjectCostsSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'count': queryset.count(),
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_overhead(request):
    """
    Create a new project overhead entry.
    
    POST /api/budget/project-overheads/
    
    Expected payload:
    {
        "project": 1,
        "overhead_type": "Contingency",
        "description": "Provided in your BOQ",
        "basis": "Percentage of BOQ",
        "percentage": 6.95,
        "amount": 5350000.00
    }
    """
    try:
        serializer = ProjectOverheadsSerializer(data=request.data)
        
        if serializer.is_valid():
            project_overhead = serializer.save()
            
            # Return the created object
            response_serializer = ProjectOverheadsSerializer(project_overhead)
            
            return Response({
                'success': True,
                'message': 'Project overhead created successfully',
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_project_overheads(request):
    """
    List all project overheads with optional filtering.
    
    GET /api/budget/project-overheads/
    
    Query parameters:
    - project_id: Filter by project ID
    - overhead_type: Filter by overhead type
    """
    try:
        queryset = ProjectOverheads.objects.all()
        
        # Apply filters if provided
        project_id = request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
            
        overhead_type = request.query_params.get('overhead_type')
        if overhead_type:
            queryset = queryset.filter(overhead_type__icontains=overhead_type)
        
        serializer = ProjectOverheadsSerializer(queryset, many=True)
        
        return Response({
            'success': True,
            'count': queryset.count(),
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_latest_data(request, project_id):
    """
    Get the latest data for a specific project including all current versions.
    
    GET /api/budget/projects/{project_id}/latest/
    
    Returns:
    - Project details
    - All current project costs with latest versions
    - All current project overheads with latest versions
    - Calculated totals
    """
    try:
        project = Projects.objects.get(id=project_id)
        serializer = ProjectLatestDataSerializer(project)
        
        return Response({
            'success': True,
            'message': 'Latest project data retrieved successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Projects.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Project not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_cost_versions(request, cost_id):
    """
    Get version history for a specific project cost item.
    
    GET /api/budget/project-costs/{cost_id}/versions/
    
    Returns all historical versions of the specified cost item.
    """
    try:
        # Check if the cost item exists
        cost_item = ProjectCosts.objects.get(id=cost_id)
        
        # Get all versions for this cost item
        versions = ProjectCostVersion.objects.filter(original_record=cost_item).order_by('-created_at')
        serializer = ProjectCostVersionSerializer(versions, many=True)
        
        # Also include current version data
        current_serializer = ProjectCostsSerializer(cost_item)
        
        return Response({
            'success': True,
            'message': 'Project cost version history retrieved successfully',
            'current_version': current_serializer.data,
            'version_history': serializer.data,
            'total_versions': versions.count() + 1  # +1 for current version
        }, status=status.HTTP_200_OK)
        
    except ProjectCosts.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Project cost item not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_overhead_versions(request, overhead_id):
    """
    Get version history for a specific project overhead item.
    
    GET /api/budget/project-overheads/{overhead_id}/versions/
    
    Returns all historical versions of the specified overhead item.
    """
    try:
        # Check if the overhead item exists
        overhead_item = ProjectOverheads.objects.get(id=overhead_id)
        
        # Get all versions for this overhead item
        versions = ProjectOverheadVersion.objects.filter(original_record=overhead_item).order_by('-created_at')
        serializer = ProjectOverheadVersionSerializer(versions, many=True)
        
        # Also include current version data
        current_serializer = ProjectOverheadsSerializer(overhead_item)
        
        return Response({
            'success': True,
            'message': 'Project overhead version history retrieved successfully',
            'current_version': current_serializer.data,
            'version_history': serializer.data,
            'total_versions': versions.count() + 1  # +1 for current version
        }, status=status.HTTP_200_OK)
        
    except ProjectOverheads.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Project overhead item not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_project_cost(request, cost_id):
    """
    Update a project cost item with version control.
    
    PUT /api/budget/project-costs/{cost_id}/
    
    This will automatically create a version record if any tracked fields change.
    """
    try:
        cost_item = ProjectCosts.objects.get(id=cost_id)
        
        # Set user context for version tracking
        cost_item._changed_by = request.user
        cost_item._change_reason = request.data.get('change_reason', 'Updated via API')
        
        serializer = ProjectCostsSerializer(cost_item, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_cost = serializer.save()
            
            response_serializer = ProjectCostsSerializer(updated_cost)
            
            return Response({
                'success': True,
                'message': 'Project cost updated successfully',
                'data': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except ProjectCosts.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Project cost item not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_project_overhead(request, overhead_id):
    """
    Update a project overhead item with version control.
    
    PUT /api/budget/project-overheads/{overhead_id}/
    
    This will automatically create a version record if any tracked fields change.
    """
    try:
        overhead_item = ProjectOverheads.objects.get(id=overhead_id)
        
        # Set user context for version tracking
        overhead_item._changed_by = request.user
        overhead_item._change_reason = request.data.get('change_reason', 'Updated via API')
        
        serializer = ProjectOverheadsSerializer(overhead_item, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_overhead = serializer.save()
            
            response_serializer = ProjectOverheadsSerializer(updated_overhead)
            
            return Response({
                'success': True,
                'message': 'Project overhead updated successfully',
                'data': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except ProjectOverheads.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Project overhead item not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
