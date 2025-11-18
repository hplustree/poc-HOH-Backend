from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from decimal import Decimal
from .models import Projects, ProjectCosts, ProjectOverheads, ProjectVersion, ProjectCostVersion, ProjectOverheadVersion
from .serializers import (PDFExtractionSerializer, ProjectSerializer, ChatAcceptRequestSerializer, 
                         ChatAcceptResponseSerializer, CostingJsonSerializer, LatestCostingResponseSerializer,
                         ProjectVersionHistoryResponseSerializer, ProjectDetailSerializer, ProjectVersionCostSerializer, 
                         ProjectVersionOverheadSerializer)
from chatapp.models import Session, Conversation, Messages
from authentication.models import UserDetail
from chatapp.utils import generate_costing_json_from_db, create_sessions_for_all_users_on_project_creation
import logging
import json
import requests
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

class PDFExtractionView(APIView):
    """
    API endpoint to handle document extraction data without affecting existing data.
    
    SUPPORTED FORMATS: PDF, DOC, DOCX, TXT, RTF
    
    WORKFLOW:
    1. Validates that uploaded file is in document format only
    2. Creates new project with incoming data (existing data remains untouched)
    3. Creates sessions and conversations for ALL verified and active users
    4. Returns comprehensive results including creation statistics and session creation results
    
    This approach preserves all existing data while adding new project data from document extraction.
    Only accepts document formats and maintains complete data history.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        # Get the filename from query params
        file_obj = request.FILES.get('files') or request.FILES.get('file')
        if file_obj:
            filename = file_obj.name
        else:
            filename = request.query_params.get('filename', '')
            if not filename:
                return Response(
                    {'error': 'Filename parameter is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate document format - only allow document formats
        allowed_extensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf']
        file_extension = None
        
        # Extract file extension
        if '.' in filename:
            file_extension = '.' + filename.split('.')[-1].lower()
        
        if not file_extension or file_extension not in allowed_extensions:
            return Response(
                {
                    'error': 'Invalid file format. Only document formats are allowed.',
                    'allowed_formats': ['PDF', 'DOC', 'DOCX', 'TXT', 'RTF'],
                    'provided_filename': filename
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the incoming data
        if file_obj:
            try:
                base_uri = os.getenv('ML_BASE_URI', 'http://0.0.0.0:8000').rstrip('/')
                upload_url = f"{base_uri}/api/upload-doc"

                files = {
                    'files': (file_obj.name, file_obj, getattr(file_obj, 'content_type', 'application/octet-stream'))
                }
                headers = {
                    'accept': 'application/json'
                }

                logger.info(f"Calling external upload-doc API for file: {file_obj.name}")
                upload_response = requests.post(upload_url, files=files, headers=headers, timeout=300)
                upload_response.raise_for_status()
                upload_data = upload_response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling upload-doc API: {str(e)}", exc_info=True)
                return Response(
                    {'error': 'Failed to process document using upload-doc API', 'message': str(e)},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from upload-doc API: {str(e)}", exc_info=True)
                return Response(
                    {'error': 'Invalid JSON response from upload-doc API', 'message': str(e)},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            serializer = PDFExtractionSerializer(data=upload_data)
        else:
            serializer = PDFExtractionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        project_data = data['project']
        cost_items = data.get('cost_line_items', [])
        overhead_items = data.get('overheads', [])
        
        try:
            # STEP 1: Create project and related data (no deletion of existing data)
            logger.info("Starting PDF extraction - creating new project without deleting existing data")
            with transaction.atomic():
                # Create new project with the incoming data
                project = Projects.objects.create(
                    name=project_data['name'],
                    location=project_data.get('location'),
                    start_date=project_data.get('start_date'),
                    end_date=project_data.get('end_date'),
                    total_cost=project_data.get('total_cost')
                )
                
                # Set change tracking attributes
                project._changed_by = f"PDF Import: {filename}"
                project._change_reason = 'Created from PDF import - fresh start'
                
                logger.info(f"Created new project: {project.name} (ID: {project.id})")
                
                # Create project costs
                costs_created = 0
                if cost_items:
                    for item in cost_items:
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
                        new_cost = ProjectCosts.objects.create(**cost_data)
                        new_cost._changed_by = f"PDF Import: {filename}"
                        new_cost._change_reason = 'Created from PDF import - fresh start'
                        costs_created += 1
                
                logger.info(f"Created {costs_created} project costs")
                
                # Create project overheads
                overheads_created = 0
                if overhead_items:
                    for item in overhead_items:
                        overhead_data = {
                            'project': project,
                            'overhead_type': item['overhead_type'],
                            'description': item.get('description'),
                            'basis': item.get('basis'),
                            'percentage': item['percentage'],
                            'amount': item['amount']
                        }
                        
                        new_overhead = ProjectOverheads.objects.create(**overhead_data)
                        new_overhead._changed_by = f"PDF Import: {filename}"
                        new_overhead._change_reason = 'Created from PDF import - fresh start'
                        overheads_created += 1
                
                logger.info(f"Created {overheads_created} project overhead items")
            
            # STEP 5: Create sessions and conversations for ALL users (separate transaction)
            session_creation_result = None
            try:
                logger.info(f"Creating sessions for all users for new project: {project.name}")
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
            
            # Return the new project with all related data
            project_serializer = ProjectSerializer(instance=project)
            response_data = {
                'status': 'success',
                'message': 'New project created successfully without affecting existing data',
                'project': project_serializer.data,
                'creation_summary': {
                    'costs_created': costs_created,
                    'overheads_created': overheads_created
                },
                'chat_session': {
                    'created': session_created,
                    'session_id': session_id,
                    'conversation_id': conversation_id
                }
            }
            
            # Include session creation results
            if session_creation_result:
                response_data['session_creation'] = session_creation_result
            
            return Response(response_data, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error processing PDF import: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to process PDF import: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def call_chatbot_decision_accept_api(approval, costing_json, answer):
    """
    Call the external chatbot-decision-accept API
    
    Args:
        approval: 'accept' or 'reject' - user's approval decision
        costing_json: The costing data dictionary
        answer: The answer text extracted from message content
    
    Returns:
        dict: API response containing status, answer, costing_json, and final_action
    """
    api_url = os.getenv('ML_BASE_URI') + "/api/chatbot-decision-accept"
    
    payload = {
        "approval": approval,
        "costing_json": costing_json,
        "answer": answer
    }
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Calling external API with approval: {approval}")
        response = requests.post(api_url, json=payload, headers=headers, timeout=3000)
        response.raise_for_status()
        
        api_response = response.json()
        logger.info(f"External API response: status={api_response.get('status')}, final_action={api_response.get('final_action')}")
        
        return api_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling external API: {str(e)}")
        raise Exception(f"Failed to call external API: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing API response: {str(e)}")
        raise Exception(f"Invalid JSON response from API: {str(e)}")


class ChatAcceptView(APIView):
    """
    API endpoint to handle chat-accept requests.
    
    Workflow:
    1. Receive message_id and approval from user
    2. Extract costing_json from message metadata
    3. Extract answer from message content
    4. Call external API with approval, costing_json, and answer
    5. Use final_action from API response to determine database updates
    6. Update message and budget based on final_action (not user approval)
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        # Validate request data
        serializer = ChatAcceptRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        message_id = serializer.validated_data['message_id']
        approval = serializer.validated_data['approval']
        
        try:
            # Step 1: Get the message
            message = Messages.objects.get(message_id=message_id)
            
            # Step 2: Extract costing_json from metadata
            metadata = message.metadata or {}
            chatbot_response = metadata.get('chatbot_response', {})
            costing_json = chatbot_response.get('costing')
            
            # Handle nested data structure if it exists, otherwise use direct structure
            if costing_json and isinstance(costing_json, dict) and 'data' in costing_json:
                costing_json = costing_json['data']
            
            if not costing_json:
                return Response(
                    {'error': 'No costing data found in message metadata'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Step 3: Extract answer from message content
            answer = message.content or ""
            
            # Step 4: Call external API
            logger.info(f"Processing chat-accept for message {message_id} with approval: {approval}")
            api_response = call_chatbot_decision_accept_api(approval, costing_json, answer)
            
            # Step 5: Validate API response
            response_serializer = ChatAcceptResponseSerializer(data=api_response)
            if not response_serializer.is_valid():
                logger.error(f"Invalid API response: {response_serializer.errors}")
                return Response(
                    {'error': 'Invalid response from external API', 'details': response_serializer.errors}, 
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Step 6: Get final_action from API response
            final_action = api_response.get('final_action')
            api_answer = api_response.get('answer', '')
            updated_costing_json = api_response.get('costing_json', {})
            
            # Step 7: Update message based on final_action
            message.is_hide = True
            if final_action == 'accept':
                message.is_accept = True
                from django.utils import timezone
                message.accepted_at = timezone.now()
            else:
                message.is_accept = False
            message.save()
            
            # Step 8: Save API answer as new assistant message
            if api_answer:
                Messages.objects.create(
                    conversation=message.conversation,
                    session=message.session,
                    message_type='assistant',
                    content=api_answer,
                    metadata={
                        'source': 'chat_accept_api',
                        'original_message_id': message_id,
                        'final_action': final_action
                    }
                )
            
            # Step 9: Update budget ONLY if final_action is 'accept'
            budget_updated = False
            if final_action == 'accept' and updated_costing_json:
                logger.info("Final action is 'accept', updating budget")
                self._update_budget(updated_costing_json, request.user)
                budget_updated = True
            else:
                logger.info(f"Final action is '{final_action}', skipping budget update")
            
            # Step 10: Return response
            return Response({
                'status': 'success',
                'message': f'Chat processed successfully',
                'final_action': final_action,
                'answer': api_answer,
                'costing_json': updated_costing_json,
                'budget_updated': budget_updated
            }, status=status.HTTP_200_OK)
            
        except Messages.DoesNotExist:
            return Response(
                {'error': 'Message not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error processing chat-accept: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to process chat-accept: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _update_budget(self, costing_json, user):
        """
        Update budget data with automatic version control
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
                        'total_cost': Decimal(str(project_data.get('total_cost', 0))) if project_data.get('total_cost') else None
                    }
                )
                
                if not created:
                    # Update existing project
                    project._changed_by = f'chat_accept_{user.username}'
                    project._change_reason = 'Updated from chat accept API'
                    
                    if project_data.get('location'):
                        project.location = project_data['location']
                    if project_data.get('start_date'):
                        project.start_date = project_data['start_date']
                    if project_data.get('end_date'):
                        project.end_date = project_data['end_date']
                    if project_data.get('total_cost') is not None:
                        project.total_cost = Decimal(str(project_data['total_cost']))
                    
                    project.save()
                
                # Update or create cost items
                for item in cost_items:
                    # Match by category_name and item_description
                    cost, created = ProjectCosts.objects.get_or_create(
                        project=project,
                        category_name=item.get('category_name'),
                        item_description=item.get('item_description'),
                        defaults={
                            'category_code': item.get('category_code'),
                            'supplier_brand': item.get('supplier_brand'),
                            'unit': item.get('unit'),
                            'quantity': Decimal(str(item.get('quantity', 0))) if item.get('quantity') else None,
                            'rate_per_unit': Decimal(str(item.get('rate_per_unit', 0))) if item.get('rate_per_unit') else None,
                            'line_total': Decimal(str(item.get('line_total', 0))) if item.get('line_total') else None,
                            'category_total': Decimal(str(item.get('category_total', 0))) if item.get('category_total') else None
                        }
                    )
                    
                    if not created:
                        # Update existing cost
                        cost._changed_by = f'chat_accept_{user.username}'
                        cost._change_reason = 'Updated from chat accept API'
                        
                        if item.get('supplier_brand'):
                            cost.supplier_brand = item['supplier_brand']
                        if item.get('unit'):
                            cost.unit = item['unit']
                        if item.get('quantity') is not None:
                            cost.quantity = Decimal(str(item['quantity']))
                        if item.get('rate_per_unit') is not None:
                            cost.rate_per_unit = Decimal(str(item['rate_per_unit']))
                        if item.get('category_total') is not None:
                            cost.category_total = Decimal(str(item['category_total']))
                        
                        cost.save()
                
                # Update or create overheads
                for item in overhead_items:
                    overhead, created = ProjectOverheads.objects.get_or_create(
                        project=project,
                        overhead_type=item.get('overhead_type'),
                        defaults={
                            'description': item.get('description'),
                            'basis': item.get('basis'),
                            'percentage': Decimal(str(item.get('percentage', 0))) if item.get('percentage') else None,
                            'amount': Decimal(str(item.get('amount', 0))) if item.get('amount') else None
                        }
                    )
                    
                    if not created:
                        # Update existing overhead
                        overhead._changed_by = f'chat_accept_{user.username}'
                        overhead._change_reason = 'Updated from chat accept API'
                        
                        if item.get('description'):
                            overhead.description = item['description']
                        if item.get('basis'):
                            overhead.basis = item['basis']
                        if item.get('percentage') is not None:
                            overhead.percentage = Decimal(str(item['percentage']))
                        if item.get('amount') is not None:
                            overhead.amount = Decimal(str(item['amount']))
                        
                        overhead.save()
                
                logger.info(f"Budget updated successfully for project: {project.name}")
                
        except Exception as e:
            logger.error(f"Error updating budget: {str(e)}", exc_info=True)
            raise


class LatestCostingView(APIView):
    """
    API endpoint to fetch latest costing_json data in the exact format required.
    Supports both latest project and specific project by ID.
    Enhanced with soft delete filtering.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_id=None, format=None):
        """
        GET /api/budget/api/latest-costing/ - Latest project costing data
        GET /api/budget/api/latest-costing/{project_id}/ - Specific project costing data
        Query params: ?include_deleted=true to include soft deleted records
        """
        try:
            # Check if we should include deleted records
            include_deleted = request.query_params.get('include_deleted', 'false').lower() == 'true'
            
            # Get costing data using the unified function
            costing_data = generate_costing_json_from_db(
                project_id=project_id, 
                include_wrapper=False,
                include_deleted=include_deleted  # Pass the parameter to the function
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
            
            logger.info(f"Successfully retrieved costing data for project_id: {project_id or 'latest'}, include_deleted: {include_deleted}")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching latest costing data: {str(e)}")
            return Response({
                'error': 'Internal server error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProjectVersionHistoryView(APIView):
    """
    API endpoint to fetch complete project version history with costs and overheads for each version.
    GET /api/budget/projects/{project_id}/version-history/
    Enhanced with soft delete filtering and soft delete operations.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_id, format=None):
        """
        Get complete project version history including all costs and overheads for each version
        Query params: ?include_deleted=true to include soft deleted records
        """
        try:
            # Check if we should include deleted records
            include_deleted = request.query_params.get('include_deleted', 'false').lower() == 'true'
            
            # Get the project
            try:
                if include_deleted:
                    project = Projects.objects.get(id=project_id)
                else:
                    project = Projects.objects.get(id=project_id, is_delete=False)
            except Projects.DoesNotExist:
                return Response({
                    'error': 'Project not found or has been deleted'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all project versions (historical data)
            project_versions = ProjectVersion.objects.filter(project=project).order_by('version_number')
            
            # Build version history data
            version_history_data = []
            
            # Add historical versions from ProjectVersion table
            for version in project_versions:
                # Get costs for this version from ProjectCostVersion table
                version_costs = ProjectCostVersion.objects.filter(
                    project=project,
                    version_number=version.version_number
                ).order_by('id')
                
                # Get overheads for this version from ProjectOverheadVersion table
                version_overheads = ProjectOverheadVersion.objects.filter(
                    project=project,
                    version_number=version.version_number
                ).order_by('id')
                
                # Serialize costs and overheads for this version
                costs_data = []
                for cost_version in version_costs:
                    costs_data.append({
                        'id': cost_version.id,
                        'category_code': cost_version.category_code,
                        'category_name': cost_version.category_name,
                        'item_description': cost_version.item_description,
                        'supplier_brand': cost_version.supplier_brand,
                        'unit': cost_version.unit,
                        'quantity': cost_version.quantity,
                        'rate_per_unit': cost_version.rate_per_unit,
                        'line_total': cost_version.line_total,
                        'category_total': cost_version.category_total
                    })
                
                overheads_data = []
                for overhead_version in version_overheads:
                    overheads_data.append({
                        'id': overhead_version.id,
                        'overhead_type': overhead_version.overhead_type,
                        'description': overhead_version.description,
                        'basis': overhead_version.basis,
                        'percentage': overhead_version.percentage,
                        'amount': overhead_version.amount
                    })
                
                version_data = {
                    'version_number': version.version_number,
                    'total_cost': version.total_cost,
                    'timestamp': version.updated_at,
                    'change_reason': version.change_reason,
                    'changed_by': version.changed_by,
                    'project_costs': costs_data,
                    'project_overheads': overheads_data
                }
                version_history_data.append(version_data)
            
            # Add current version (from main tables)
            current_costs = ProjectCosts.objects.filter(project=project).order_by('id')
            current_overheads = ProjectOverheads.objects.filter(project=project).order_by('id')
            
            # Serialize current costs and overheads
            current_costs_data = ProjectVersionCostSerializer(current_costs, many=True).data
            current_overheads_data = ProjectVersionOverheadSerializer(current_overheads, many=True).data
            
            # Add current version to history
            current_version_data = {
                'version_number': project.version_number,
                'total_cost': project.total_cost,
                'timestamp': project.updated_at,
                'change_reason': 'Current version',
                'changed_by': 'system',
                'project_costs': current_costs_data,
                'project_overheads': current_overheads_data
            }
            version_history_data.append(current_version_data)
            
            # Sort by version number
            version_history_data.sort(key=lambda x: x['version_number'])
            
            # Prepare response data
            response_data = {
                'status': 'success',
                'message': f'Retrieved complete project version history for {project.name}',
                'project_detail': ProjectDetailSerializer(project).data,
                'project_versions': version_history_data
            }
            
            logger.info(f"Successfully retrieved version history for project {project_id} with {len(version_history_data)} versions")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching project version history: {str(e)}", exc_info=True)
            return Response({
                'error': 'Internal server error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProjectListView(APIView):
    """
    API endpoint to fetch all projects with optional soft delete filtering.
    Includes latest session_id for each project for the authenticated user.
    
    GET /api/budget/projects/
    Query params: ?include_deleted=true to include soft deleted projects
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        Get all projects with optional soft delete filtering and latest session_id
        """
        try:
            # Check if we should include deleted records
            include_deleted = request.query_params.get('include_deleted', 'false').lower() == 'true'
            
            # Get current user's UserDetail
            try:
                user_detail = UserDetail.objects.get(email=request.user.email)
            except UserDetail.DoesNotExist:
                return Response({
                    'error': 'User profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Filter projects based on soft delete status
            if include_deleted:
                projects = Projects.objects.all().order_by('-updated_at')
                logger.info(f"Fetching all projects including deleted ones for user: {request.user.username}")
            else:
                projects = Projects.objects.filter(is_delete=False).order_by('-updated_at')
                logger.info(f"Fetching active projects only for user: {request.user.username}")
            
            # Serialize the projects
            serialized_projects = ProjectSerializer(projects, many=True).data
            
            # Add latest session_id for each project
            for project_data in serialized_projects:
                project_id = project_data['id']
                
                # Get latest session for this user and project
                try:
                    latest_session = Session.objects.filter(
                        user_id=user_detail,
                        project_id=project_id,
                        is_delete=False
                    ).order_by('-updated_at').first()
                    
                    if latest_session:
                        project_data['session_id'] = latest_session.session_id
                    else:
                        project_data['session_id'] = None
                        
                except Exception as session_error:
                    logger.warning(f"Error getting session for project {project_id}: {str(session_error)}")
                    project_data['session_id'] = None
            
            response_data = {
                'status': 'success',
                'count': len(serialized_projects),
                'include_deleted': include_deleted,
                'projects': serialized_projects
            }
            
            logger.info(f"Successfully retrieved {len(serialized_projects)} projects with session info")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching projects: {str(e)}")
            return Response({
                'error': 'Internal server error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


