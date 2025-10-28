from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from .models import Projects, ProjectCosts, ProjectOverheads
from .serializers import PDFExtractionSerializer, ProjectSerializer, ChatAcceptRequestSerializer, ChatAcceptResponseSerializer, CostingJsonSerializer, LatestCostingResponseSerializer
from rest_framework.permissions import IsAuthenticated
from chatapp.models import Session, Conversation
from authentication.models import UserDetail
from chatapp.utils import generate_costing_json_from_db, create_sessions_for_all_users_on_project_creation
import logging
import json
import requests

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
                        'total_cost': project_data.get('total_cost')
                    }
                )
                
                # Set change tracking attributes after creation/retrieval
                if created:
                    project._changed_by = f"PDF Import: {filename}"
                    project._change_reason = 'Created from PDF import'
                
                # If project exists, update it and create a new version if needed
                if not created:
                    update_fields = {}
                    tracked_fields = ['location', 'start_date', 'end_date', 'total_cost']
                    
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
                            'category_total': item.get('category_total')
                        }
                        
                        if existing_cost:
                            # Update existing cost item
                            existing_cost._changed_by = f"PDF Import: {filename}"
                            existing_cost._change_reason = 'Updated from PDF import'
                            
                            for field, value in cost_data.items():
                                if field != 'project':
                                    setattr(existing_cost, field, value)
                            existing_cost.save()
                            
                            # Remove from existing_costs dict to track which items were not in the import
                            if existing_cost.id in existing_costs:
                                del existing_costs[existing_cost.id]
                        else:
                            # Create new cost item
                            new_cost = ProjectCosts.objects.create(**cost_data)
                            new_cost._changed_by = f"PDF Import: {filename}"
                            new_cost._change_reason = 'Created from PDF import'
                    
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
                            'amount': item['amount']
                        }
                        
                        if existing_overhead:
                            # Update existing overhead
                            existing_overhead._changed_by = f"PDF Import: {filename}"
                            existing_overhead._change_reason = 'Updated from PDF import'
                            
                            for field, value in overhead_data.items():
                                if field != 'project':
                                    setattr(existing_overhead, field, value)
                            existing_overhead.save()
                            
                            # Remove from existing_overheads dict to track which items were not in the import
                            if existing_overhead.id in existing_overheads:
                                del existing_overheads[existing_overhead.id]
                        else:
                            # Create new overhead
                            new_overhead = ProjectOverheads.objects.create(**overhead_data)
                            new_overhead._changed_by = f"PDF Import: {filename}"
                            new_overhead._change_reason = 'Created from PDF import'
                    
                    # Delete any overheads that were not in the import
                    for overhead_to_delete in existing_overheads.values():
                        overhead_to_delete.delete()
                
                # Create sessions for all users if this is a new project
                session_creation_result = None
                if created:
                    try:
                        logger.info(f"New project created: {project.name}. Creating sessions for all users.")
                        session_creation_result = create_sessions_for_all_users_on_project_creation(project)
                        logger.info(f"Session creation completed: {session_creation_result}")
                    except Exception as session_error:
                        logger.error(f"Error creating sessions for all users: {str(session_error)}", exc_info=True)
                        session_creation_result = {
                            "success": False,
                            "error": f"Failed to create sessions: {str(session_error)}"
                        }
                
                # Get current user's session info for response
                session_created = False
                session_id = None
                conversation_id = None
                try:
                    user_detail = UserDetail.objects.filter(email=request.user.email).first()
                    if user_detail:
                        user_session = Session.objects.filter(
                            user_id=user_detail,
                            project_id=project
                        ).first()
                        if user_session:
                            session_id = user_session.session_id
                            session_created = True
                            # Get conversation for this session
                            conversation = Conversation.objects.filter(session=user_session).first()
                            if conversation:
                                conversation_id = conversation.conversation_id
                except Exception as e:
                    logger.error(f"Error getting user session info: {str(e)}")
                
                # Return the updated project with all related data
                project_serializer = ProjectSerializer(instance=project)
                response_data = {
                    'status': 'success',
                    'message': 'Project created/updated successfully',
                    'project': project_serializer.data,
                    'chat_session': {
                        'created': session_created,
                        'session_id': session_id,
                        'conversation_id': conversation_id
                    }
                }
                
                # Include session creation results for new projects
                if created and session_creation_result:
                    response_data['session_creation'] = session_creation_result
                
                return Response(response_data, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error processing PDF import: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to process PDF import: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def call_chatbot_decision_accept_api(approval, costing_json):
    """
    Utility function to call the external chatbot-decision-accept API
    """
    api_url = "http://0.0.0.0:8000/api/chatbot-decision-accept"
    
    payload = {
        "approval": approval,
        "costing_json": costing_json
    }
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Calling chatbot decision accept API with approval: {approval}")
        response = requests.post(api_url, json=payload, headers=headers, timeout=300)
        response.raise_for_status()
        
        api_response = response.json()
        logger.info(f"Chatbot API response received: {api_response.get('status', 'unknown')}")
        
        return api_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling chatbot decision accept API: {str(e)}")
        raise Exception(f"Failed to call chatbot API: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing chatbot API response: {str(e)}")
        raise Exception(f"Invalid response from chatbot API: {str(e)}")


class ChatAcceptView(APIView):
    """
    API endpoint to handle chat-accept requests with message_id.
    Retrieves costing_json from message metadata, calls external API, and updates budget.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        # Validate the incoming data
        serializer = ChatAcceptRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        message_id = serializer.validated_data['message_id']
        approval = serializer.validated_data['approval']
        
        try:
            # Get the message and extract costing data from metadata
            message = Messages.objects.get(message_id=message_id)
            chatbot_response = message.metadata.get('chatbot_response', {})
            costing_data = chatbot_response.get('costing', {})
            
            if not costing_data:
                return Response(
                    {'error': 'No costing data found in message metadata'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update the original message to hide it
            message.is_hide = True
            message.save()
            
            # If approval is 'reject', just return success without calling external API
            if approval == 'reject':
                return Response({
                    'status': 'success',
                    'message': 'Message rejected and hidden successfully',
                    'approval': approval
                }, status=status.HTTP_200_OK)
            
            # Extract the actual costing_json from the nested structure for 'accept' approval
            costing_json = costing_data.get('data', costing_data)
            # Call the external chatbot decision accept API
            api_response = call_chatbot_decision_accept_api(approval, costing_json)
            
            # Validate the API response
            response_serializer = ChatAcceptResponseSerializer(data=api_response)
            if not response_serializer.is_valid():
                logger.error(f"Invalid API response: {response_serializer.errors}")
                return Response(
                    {'error': 'Invalid response from chatbot API', 'details': response_serializer.errors}, 
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Save the chatbot answer as a new message
            answer = api_response.get('answer', '')
            if answer:
                Messages.objects.create(
                    conversation=message.conversation,
                    session=message.session,
                    message_type='assistant',
                    content=answer,
                    metadata={'source': 'chat_accept_api', 'original_message_id': message_id}
                )
            
            # Update the budget with version control for 'accept' approval
            updated_costing_json = api_response.get('costing_json', {})
            if updated_costing_json:
                self._update_budget_with_version_control(updated_costing_json, request.user)
            
            return Response({
                'status': 'success',
                'message': f'Chat accept processed successfully with approval: {approval}',
                'answer': answer,
                'costing_json': api_response.get('costing_json', {})
            }, status=status.HTTP_200_OK)
            
        except Messages.DoesNotExist:
            return Response(
                {'error': 'Message not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error processing chat accept: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to process chat accept: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _update_budget_with_version_control(self, costing_json, user):
        """
        Update budget data with automatic version control based on costing_json
        """
        try:
            with transaction.atomic():
                project_data = costing_json.get('project', {})
                cost_items = costing_json.get('cost_line_items', [])
                overhead_items = costing_json.get('overheads', [])
                
                if not project_data.get('name'):
                    logger.warning("No project name found in costing_json")
                    return
                
                # Find or create project
                project, created = Projects.objects.get_or_create(
                    name=project_data['name'],
                    defaults={
                        'location': project_data.get('location'),
                        'start_date': project_data.get('start_date'),
                        'end_date': project_data.get('end_date'),
                        'total_cost': project_data.get('total_cost'),
                        '_changed_by': f'chat_accept_{user.username}',
                        '_change_reason': 'Updated from chat accept API'
                    }
                )
                
                # If project exists, update it with version control
                if not created:
                    update_fields = {}
                    tracked_fields = ['location', 'start_date', 'end_date', 'total_cost']
                    
                    for field in tracked_fields:
                        if field in project_data and getattr(project, field) != project_data[field]:
                            update_fields[field] = project_data[field]
                    
                    if update_fields:
                        project._changed_by = f'chat_accept_{user.username}'
                        project._change_reason = 'Updated from chat accept API'
                        
                        for field, value in update_fields.items():
                            setattr(project, field, value)
                        project.save()
                
                # Update project costs with version control
                if cost_items:
                    for item in cost_items:
                        # Find existing cost item
                        existing_costs = ProjectCosts.objects.filter(
                            project=project,
                            category_code=item.get('category_code'),
                            item_description=item.get('item_description')
                        )
                        
                        if existing_costs.exists():
                            # Update existing cost item with version control
                            existing_cost = existing_costs.first()
                            
                            # Set change tracking attributes
                            existing_cost._changed_by = f'chat_accept_{user.username}'
                            existing_cost._change_reason = 'Updated from chat accept API'
                            
                            # Update fields
                            existing_cost.quantity = item.get('quantity', existing_cost.quantity)
                            existing_cost.rate_per_unit = item.get('rate_per_unit', existing_cost.rate_per_unit)
                            existing_cost.supplier_brand = item.get('supplier_brand', existing_cost.supplier_brand)
                            existing_cost.category_total = item.get('category_total', existing_cost.category_total)
                            existing_cost.unit = item.get('unit', existing_cost.unit)
                            existing_cost.category_name = item.get('category_name', existing_cost.category_name)
                            
                            existing_cost.save()
                        else:
                            # Create new cost item
                            ProjectCosts.objects.create(
                                project=project,
                                category_code=item.get('category_code'),
                                category_name=item.get('category_name'),
                                item_description=item.get('item_description'),
                                supplier_brand=item.get('supplier_brand'),
                                unit=item.get('unit'),
                                quantity=item.get('quantity', 0),
                                rate_per_unit=item.get('rate_per_unit', 0),
                                line_total=item.get('line_total', 0),
                                category_total=item.get('category_total'),
                                _changed_by=f'chat_accept_{user.username}',
                                _change_reason='Created from chat accept API'
                            )
                
                # Update project overheads with version control
                if overhead_items:
                    for item in overhead_items:
                        existing_overheads = ProjectOverheads.objects.filter(
                            project=project,
                            overhead_type=item.get('overhead_type')
                        )
                        
                        if existing_overheads.exists():
                            # Update existing overhead with version control
                            existing_overhead = existing_overheads.first()
                            
                            existing_overhead._changed_by = f'chat_accept_{user.username}'
                            existing_overhead._change_reason = 'Updated from chat accept API'
                            
                            existing_overhead.description = item.get('description', existing_overhead.description)
                            existing_overhead.basis = item.get('basis', existing_overhead.basis)
                            existing_overhead.percentage = item.get('percentage', existing_overhead.percentage)
                            existing_overhead.amount = item.get('amount', existing_overhead.amount)
                            
                            existing_overhead.save()
                        else:
                            # Create new overhead
                            ProjectOverheads.objects.create(
                                project=project,
                                overhead_type=item.get('overhead_type'),
                                description=item.get('description'),
                                basis=item.get('basis'),
                                percentage=item.get('percentage', 0),
                                amount=item.get('amount', 0),
                                _changed_by=f'chat_accept_{user.username}',
                                _change_reason='Created from chat accept API'
                            )
                
                logger.info(f"Budget updated successfully for project: {project.name}")
                
        except Exception as e:
            logger.error(f"Error updating budget with version control: {str(e)}")
            raise


class LatestCostingView(APIView):
    """
    API endpoint to fetch latest costing_json data in the exact format required.
    Supports both latest project and specific project by ID.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_id=None, format=None):
        """
        GET /api/budget/api/latest-costing/ - Latest project costing data
        GET /api/budget/api/latest-costing/{project_id}/ - Specific project costing data
        """
        try:
            # Get costing data using the unified function
            costing_data = generate_costing_json_from_db(
                project_id=project_id, 
                include_wrapper=False
            )
            
            # Handle error cases
            if costing_data.get("status") == "error":
                return Response({
                    'error': 'Project not found or no costing data available',
                    'message': costing_data.get('message', 'Unknown error')
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Wrap in the expected response format
            response_data = {
                "costing_json": costing_data
            }
            
            # Validate response
            serializer = LatestCostingResponseSerializer(data=response_data)
            if not serializer.is_valid():
                logger.error(f"Invalid costing data structure: {serializer.errors}")
                return Response({
                    'error': 'Invalid costing data structure',
                    'details': serializer.errors
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info(f"Successfully retrieved costing data for project_id: {project_id or 'latest'}")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching latest costing data: {str(e)}")
            return Response({
                'error': 'Internal server error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
