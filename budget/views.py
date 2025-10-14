from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from .models import Projects, ProjectCosts, ProjectOverheads
from .serializers import PDFExtractionSerializer, ProjectSerializer
from rest_framework.permissions import IsAuthenticated
import logging

logger = logging.getLogger(__name__)

class PDFExtractionView(APIView):
    """
    API endpoint to handle PDF extraction data and create/update projects with version control.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        # Get the filename from query params
        filename = request.query_params.get('filename', '')
        if not filename:
            return Response(
                {'error': 'Filename parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the incoming data
        serializer = PDFExtractionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        project_data = data['project']
        cost_items = data.get('cost_line_items', [])
        overhead_items = data.get('overheads', [])
        
        try:
            with transaction.atomic():
                # Find or create project
                project, created = Projects.objects.get_or_create(
                    name=project_data['name'],
                    defaults={
                        'location': project_data.get('location'),
                        'start_date': project_data.get('start_date'),
                        'end_date': project_data.get('end_date'),
                        '_changed_by': f"PDF Import: {filename}",
                        '_change_reason': 'Created from PDF import' if created else 'Updated from PDF import'
                    }
                )
                
                # If project exists, update it and create a new version if needed
                if not created:
                    update_fields = {}
                    tracked_fields = ['location', 'start_date', 'end_date']
                    
                    for field in tracked_fields:
                        if field in project_data and getattr(project, field) != project_data[field]:
                            update_fields[field] = project_data[field]
                    
                    if update_fields:
                        # Set change tracking attributes
                        project._changed_by = f"PDF Import: {filename}"
                        project._change_reason = 'Updated from PDF import'
                        
                        # Update fields
                        for field, value in update_fields.items():
                            setattr(project, field, value)
                        project.save()
                
                # Handle project costs
                if cost_items:
                    # Get existing cost items to compare
                    existing_costs = {cost.id: cost for cost in project.costs.all()}
                    
                    for item in cost_items:
                        # Try to find existing cost item with same description and category
                        existing_cost = next(
                            (cost for cost in existing_costs.values() 
                             if cost.item_description == item['item_description'] 
                             and cost.category_code == item['category_code']),
                            None
                        )
                        
                        cost_data = {
                            'project': project,
                            'category_code': item['category_code'],
                            'category_name': item['category_name'],
                            'item_description': item['item_description'],
                            'supplier_brand': item.get('supplier_brand'),
                            'unit': item.get('unit'),
                            'quantity': item['quantity'],
                            'rate_per_unit': item['rate_per_unit'],
                            'line_total': item['line_total'],
                            'category_total': item.get('category_total'),
                            '_changed_by': f"PDF Import: {filename}",
                            '_change_reason': 'Created from PDF import' if not existing_cost else 'Updated from PDF import'
                        }
                        
                        if existing_cost:
                            # Update existing cost item
                            for field, value in cost_data.items():
                                if field not in ['project', '_changed_by', '_change_reason']:
                                    setattr(existing_cost, field, value)
                            existing_cost.save()
                            
                            # Remove from existing_costs dict to track which items were not in the import
                            if existing_cost.id in existing_costs:
                                del existing_costs[existing_cost.id]
                        else:
                            # Create new cost item
                            ProjectCosts.objects.create(**cost_data)
                    
                    # Delete any cost items that were not in the import
                    for cost_to_delete in existing_costs.values():
                        cost_to_delete.delete()
                
                # Handle project overheads
                if overhead_items:
                    # Get existing overheads to compare
                    existing_overheads = {overhead.id: overhead for overhead in project.overheads.all()}
                    
                    for item in overhead_items:
                        # Try to find existing overhead with same type
                        existing_overhead = next(
                            (oh for oh in existing_overheads.values() 
                             if oh.overhead_type == item['overhead_type']),
                            None
                        )
                        
                        overhead_data = {
                            'project': project,
                            'overhead_type': item['overhead_type'],
                            'description': item.get('description'),
                            'basis': item.get('basis'),
                            'percentage': item['percentage'],
                            'amount': item['amount'],
                            '_changed_by': f"PDF Import: {filename}",
                            '_change_reason': 'Created from PDF import' if not existing_overhead else 'Updated from PDF import'
                        }
                        
                        if existing_overhead:
                            # Update existing overhead
                            for field, value in overhead_data.items():
                                if field not in ['project', '_changed_by', '_change_reason']:
                                    setattr(existing_overhead, field, value)
                            existing_overhead.save()
                            
                            # Remove from existing_overheads dict to track which items were not in the import
                            if existing_overhead.id in existing_overheads:
                                del existing_overheads[existing_overhead.id]
                        else:
                            # Create new overhead
                            ProjectOverheads.objects.create(**overhead_data)
                    
                    # Delete any overheads that were not in the import
                    for overhead_to_delete in existing_overheads.values():
                        overhead_to_delete.delete()
                
                # Return the updated project with all related data
                project_serializer = ProjectSerializer(instance=project)
                return Response({
                    'status': 'success',
                    'message': 'Project created/updated successfully',
                    'project': project_serializer.data
                }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error processing PDF import: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to process PDF import: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
