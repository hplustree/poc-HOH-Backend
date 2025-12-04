from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from decimal import Decimal
from .models import Projects, ProjectCosts, ProjectOverheads, ProjectVersion, ProjectCostVersion, ProjectOverheadVersion
from .serializers import (PDFExtractionSerializer, ProjectSerializer, ChatAcceptRequestSerializer, 
                         ChatAcceptResponseSerializer, LatestCostingResponseSerializer,
                         ProjectDetailSerializer, ProjectVersionCostSerializer, 
                         ProjectVersionOverheadSerializer, ProjectDecisionGraphResponseSerializer)
from chatapp.models import Session, Conversation, Messages
from news.models import Alert
from authentication.models import UserDetail
from chatapp.utils import generate_costing_json_from_db
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
    
    SUPPORTED FORMATS: PDF, DOC, DOCX, TXT, RTF, CSV
    
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
        external_project_id = None
        external_version_number = None

        # Support multiple file uploads while preserving legacy single-file/filename usage
        uploaded_files = request.FILES.getlist('files') or []
        single_file = request.FILES.get('file')

        # If only a single "files" entry was sent (not as a list), Django may expose it via get() not getlist()
        if not uploaded_files:
            file_from_files_key = request.FILES.get('files')
            if file_from_files_key is not None:
                uploaded_files = [file_from_files_key]

        # Determine filename for validation and logging (first file or fallback to query param)
        if uploaded_files:
            filename = uploaded_files[0].name
        elif single_file:
            filename = single_file.name
        else:
            filename = request.query_params.get('filename', '')
            if not filename:
                return Response(
                    {'error': 'Filename parameter is required when no files are uploaded'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate document format - only allow document formats
        allowed_extensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.xls', '.xlsx', '.csv']
        file_extension = None
        
        # Extract file extension
        if '.' in filename:
            file_extension = '.' + filename.split('.')[-1].lower()
        
        if not file_extension or file_extension not in allowed_extensions:
            return Response(
                {
                    'error': 'Invalid file format. Only document formats are allowed.',
                    'allowed_formats': ['PDF', 'DOC', 'DOCX', 'TXT', 'RTF', 'XLS', 'XLSX', 'CSV'],
                    'provided_filename': filename
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the incoming data / call external upload-doc API when files are provided
        if uploaded_files or single_file:
            try:
                base_uri = os.getenv('ML_BASE_URI', 'http://0.0.0.0:8000').rstrip('/')
                upload_url = f"{base_uri}/api/upload-doc"

                # Build multipart files payload to support multiple documents
                files_payload = []
                target_files = uploaded_files or [single_file]
                for f in target_files:
                    files_payload.append(
                        (
                            'files',
                            (
                                f.name,
                                f,
                                getattr(f, 'content_type', 'application/octet-stream')
                            ),
                        )
                    )

                headers = {
                    'accept': 'application/json'
                }

                logger.info(
                    f"Calling external upload-doc API for {len(target_files)} file(s): "
                    + ", ".join([f.name for f in target_files])
                )
                upload_response = requests.post(upload_url, files=files_payload, headers=headers, timeout=300)
                upload_response.raise_for_status()
                upload_data = upload_response.json()

                # /upload-doc wraps the extraction payload under 'data'
                external_project_id = upload_data.get('project_id')
                version_id = upload_data.get('version_id')
                if version_id is not None:
                    try:
                        external_version_number = int(version_id)
                    except (TypeError, ValueError):
                        logger.warning(f"Invalid version_id from upload-doc API response: {version_id}")
                extraction_payload = upload_data.get('data', upload_data)
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

            serializer = PDFExtractionSerializer(data=extraction_payload)
        else:
            # For legacy usage where frontend sends JSON directly, also allow a 'data' wrapper
            if isinstance(request.data, dict) and 'data' in request.data:
                serializer_input = request.data['data']
            else:
                serializer_input = request.data
            serializer = PDFExtractionSerializer(data=serializer_input)
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
                project_kwargs = {
                    'name': project_data['name'],
                    'location': project_data.get('location'),
                    'start_date': project_data.get('start_date'),
                    'end_date': project_data.get('end_date'),
                    'total_cost': project_data.get('total_cost'),
                }
                if external_project_id:
                    project_kwargs['project_id'] = external_project_id
                if external_version_number is not None:
                    project_kwargs['version_number'] = external_version_number
                project = Projects.objects.create(**project_kwargs)
                
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
                        if external_version_number is not None:
                            cost_data['version_number'] = external_version_number
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
                        if external_version_number is not None:
                            overhead_data['version_number'] = external_version_number
                        new_overhead = ProjectOverheads.objects.create(**overhead_data)
                        new_overhead._changed_by = f"PDF Import: {filename}"
                        new_overhead._change_reason = 'Created from PDF import - fresh start'
                        overheads_created += 1
                
                logger.info(f"Created {overheads_created} project overhead items")
            
            # STEP 5: Create session and conversation for the current user only (separate transaction)
            session_creation_result = None
            try:
                user_detail = UserDetail.objects.filter(email=request.user.email).first()
                if user_detail:
                    existing_session = Session.objects.filter(
                        user_id=user_detail,
                        project_id=project,
                        is_delete=False
                    ).order_by('-updated_at').first()
                    if not existing_session:
                        session = Session.objects.create(
                            project_id=project,
                            user_id=user_detail,
                            is_active=True
                        )
                        conversation = Conversation.objects.create(
                            session=session,
                            project_id=project
                        )
                        welcome_message = (
                            f"Welcome to {project.name}! I'm your AI assistant ready to help you with "
                            f"project-related questions and cost management."
                        )
                        Messages.objects.create(
                            conversation=conversation,
                            session=session,
                            sender=None,  # AI message
                            message_type='assistant',
                            content=welcome_message,
                            metadata={
                                'welcome_message': True,
                                'project_info': {
                                    'name': project.name,
                                    'location': project.location or ""
                                }
                            }
                        )
                        session_creation_result = {
                            "success": True,
                            "users_processed": 1,
                            "sessions_created": 1,
                            "conversations_created": 1,
                            "errors": []
                        }
                    else:
                        session_creation_result = {
                            "success": True,
                            "users_processed": 1,
                            "sessions_created": 0,
                            "conversations_created": 0,
                            "errors": []
                        }
                else:
                    session_creation_result = {
                        "success": False,
                        "error": "User profile not found for authenticated user"
                    }
            except Exception as session_error:
                logger.error(
                    f"Error creating session for current user and project '{project.name}': {str(session_error)}",
                    exc_info=True
                )
                if not session_creation_result:
                    session_creation_result = {
                        "success": False,
                        "error": f"Failed to create session: {str(session_error)}"
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
                'project_id': str(project.project_id),
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


def call_chatbot_decision_accept_api(approval, costing_json, answer, project_id=None, version_id=None):
    """
    Call the external chatbot-decision-accept API
    
    Args:
        approval: 'accept' or 'reject' - user's approval decision
        costing_json: The costing data dictionary
        answer: The answer text extracted from message content
        project_id: The project ID (optional)
        version_id: The version ID (optional)
    
    Returns:
        dict: API response containing status, answer, costing_json, and final_action
    """
    api_url = os.getenv('ML_BASE_URI') + "/api/chatbot-decision-accept"
    
    payload = {
        "approval": approval,
        "costing_json": costing_json,
        "answer": answer
    }
    
    if project_id:
        payload["project_id"] = project_id
    if version_id:
        payload["version_id"] = version_id
    
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
        project_id = serializer.validated_data.get('project_id')
        version_id = serializer.validated_data.get('version_id')

        if approval == 'accept' and version_id is not None:
            try:
                version_id = str(int(version_id) + 1)
            except (ValueError, TypeError):
                logger.warning(f"Could not increment version_id: {version_id}")
        
        try:
            # Step 1: Get the message
            message = Messages.objects.get(message_id=message_id)
            
            # Step 2: Extract costing_json from metadata
            metadata = message.metadata or {}
            chatbot_response = metadata.get('chatbot_response', {})
            costing_json = chatbot_response.get('costing')

            # Prefer project_id and version_id from metadata if available
            metadata_project_id = chatbot_response.get('project_id')
            metadata_version_id = chatbot_response.get('version_id')
            if metadata_project_id:
                project_id = metadata_project_id
            if metadata_version_id:
                version_id = metadata_version_id

            # Handle nested data structure if it exists, otherwise use direct structure
            if costing_json and isinstance(costing_json, dict) and 'data' in costing_json:
                costing_json = costing_json['data']
            
            if not costing_json:
                return Response(
                    {'error': 'No costing data found in message metadata'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Step 3: Extract answer (prefer chatbot_response.answer, fallback to message content)
            answer = chatbot_response.get('answer') or (message.content or "")
            
            # Step 4: Call external API
            logger.info(f"Processing chat-accept for message {message_id} with approval: {approval}, project_id: {project_id}, version_id: {version_id}")
            api_response = call_chatbot_decision_accept_api(approval, costing_json, answer, project_id, version_id)
            
            # Step 5: Validate API response
            response_serializer = ChatAcceptResponseSerializer(data=api_response)
            if not response_serializer.is_valid():
                logger.error(f"Invalid API response: {response_serializer.errors}")
                return Response(
                    {'error': 'Invalid response from external API', 'details': response_serializer.errors}, 
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Step 6: Get final_action and related data from API response
            final_action = api_response.get('final_action')
            api_answer = api_response.get('answer', '')
            updated_costing_json = api_response.get('costing_json', {})
            api_project_id = api_response.get('project_id')
            api_version_str = api_response.get('version')
            previous_version = api_response.get('previous_version')

            # Determine project UUID for update (prefer API response, fallback to metadata/request)
            project_uuid_for_update = api_project_id or project_id

            # Parse version string to int only when final_action is 'accept'
            version_int = None
            if final_action == 'accept' and api_version_str is not None:
                try:
                    version_int = int(api_version_str)
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse version from API response: {api_version_str}")
            
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
                        'final_action': final_action,
                        'project_id': project_uuid_for_update,
                        'version': version_int,
                        'previous_version': previous_version
                    }
                )
            
            # Step 9: Update budget ONLY if final_action is 'accept'
            budget_updated = False
            if final_action == 'accept' and updated_costing_json:
                logger.info("Final action is 'accept', updating budget")
                self._update_budget(updated_costing_json, request.user, project_uuid_for_update, version_int)
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
                'budget_updated': budget_updated,
                'project_id': project_uuid_for_update,
                'version': version_int,
                'previous_version': previous_version
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
    
    def _update_budget(self, costing_json, user, project_uuid=None, version=None):
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
                
                # Find project by UUID if available, otherwise fall back to name-based lookup
                project = None
                created = False
                if project_uuid:
                    project = Projects.objects.filter(project_id=project_uuid).first()
                if project is None:
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
            
            # Find projects linked to this user via chat sessions
            user_project_ids = Session.objects.filter(
                user_id=user_detail,
                is_delete=False
            ).values_list('project_id', flat=True).distinct()

            # Filter projects based on soft delete status and user sessions
            if include_deleted:
                projects = Projects.objects.filter(id__in=user_project_ids).order_by('-updated_at')
                logger.info(
                    f"Fetching all projects (including deleted) for user: {request.user.username}"
                )
            else:
                projects = Projects.objects.filter(
                    id__in=user_project_ids,
                    is_delete=False
                ).order_by('-updated_at')
                logger.info(
                    f"Fetching active projects only for user: {request.user.username}"
                )
            
            # Serialize the projects
            serialized_projects = ProjectSerializer(projects, many=True).data

            # Map DB PK -> public UUID for quick lookup
            project_uuid_map = {p.id: str(p.project_id) for p in projects}
            
            # Add latest session_id for each project and expose UUID as 'id'
            for project_data in serialized_projects:
                # Current value is DB PK from serializer
                project_pk = project_data['id']
                # Preserve DB primary key explicitly under project_id
                project_data['project_id'] = project_pk
                
                # Get latest session for this user and project (by PK)
                try:
                    latest_session = Session.objects.filter(
                        user_id=user_detail,
                        project_id=project_pk,
                        is_delete=False
                    ).order_by('-updated_at').first()
                    
                    if latest_session:
                        project_data['session_id'] = latest_session.session_id
                    else:
                        project_data['session_id'] = None
                        
                except Exception as session_error:
                    logger.warning(f"Error getting session for project {project_pk}: {str(session_error)}")
                    project_data['session_id'] = None

                # Replace 'id' with the project's public UUID (Projects.project_id)
                project_data['id'] = project_uuid_map.get(project_pk)
            
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



class ProjectDecisionGraphView(APIView):
    """API endpoint to fetch a decision graph for a project with all versions and decisions.
    
    GET /api/budget/projects/{project_id}/decision-graph/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, format=None):
        try:
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

            # Build version nodes (historical versions + current)
            project_versions = ProjectVersion.objects.filter(project=project).order_by('version_number')
            version_nodes = []

            for version in project_versions:
                base_data = self._build_base_data_for_version(project, version.version_number, historical=True, version_obj=version)
                version_nodes.append({
                    'version_number': version.version_number,
                    'created_from_version': version.version_number - 1 if version.version_number > 1 else None,
                    'created_by_decisions': [],
                    'base_data': base_data,
                    'decisions': [],
                    'version_note': version.change_reason or ''
                })

            # Current version node from main tables
            current_base_data = self._build_base_data_for_version(project, project.version_number, historical=False)
            version_nodes.append({
                'version_number': project.version_number,
                'created_from_version': project.version_number - 1 if project.version_number > 1 else None,
                'created_by_decisions': [],
                'base_data': current_base_data,
                'decisions': [],
                'version_note': 'Current version'
            })

            # Sort by version number and prepare timestamp map
            version_nodes.sort(key=lambda x: x['version_number'])
            version_index_map = {node['version_number']: idx for idx, node in enumerate(version_nodes)}

            version_timestamps = {}
            for version in project_versions:
                version_timestamps[version.version_number] = version.updated_at
            version_timestamps[project.version_number] = project.updated_at

            # Collect all decisions (news alerts + chat decisions)
            decisions = []

            # News alerts
            alerts_qs = Alert.objects.filter(project_id=project).order_by('created_at')
            for alert in alerts_qs:
                decided_at = alert.accepted_at or alert.updated_at or alert.created_at
                if alert.is_accept is True:
                    status_value = 'accepted'
                    final_action = 'accept'
                elif alert.is_accept is False:
                    status_value = 'rejected'
                    final_action = 'reject'
                else:
                    status_value = 'pending'
                    final_action = 'pending'

                decision = {
                    'decision_id': f'news-{alert.alert_id}',
                    'source': 'news_alert',
                    'question': alert.decision,
                    'status': status_value,
                    'final_action': final_action,
                    'values_before': {
                        'category_name': alert.category_name,
                        'item_description': alert.item,
                        'supplier_brand': alert.old_supplier_brand,
                        'rate_per_unit': alert.old_rate_per_unit,
                        'line_total': alert.old_line_total,
                    },
                    'values_after': {
                        'category_name': alert.category_name,
                        'item_description': alert.item,
                        'supplier_brand': alert.new_supplier_brand,
                        'rate_per_unit': alert.new_rate_per_unit,
                        'line_total': alert.new_line_total,
                    },
                    'values_after_proposed': {},
                    'decided_at': decided_at,
                    'metadata': {
                        'alert_id': alert.alert_id,
                        'decision_key': alert.decision_key,
                        'reason': alert.reason,
                        'suggestion': alert.suggestion,
                        'cost_impact': alert.cost_impact,
                    },
                }
                decisions.append(decision)

            # Chat-based decisions (message accept/reject) using is_hide/is_accept rule
            chat_qs = Messages.objects.filter(
                conversation__project_id=project,
                is_delete=False,
                is_hide=True,
            ).filter(is_accept__isnull=False).order_by('created_at')

            for message in chat_qs:
                decided_at = message.accepted_at or message.updated_at or message.created_at

                # Apply interpretation rule:
                # is_hide = True and is_accept = True  -> accepted
                # is_hide = True and is_accept = False -> rejected
                if message.is_accept is True:
                    status_value = 'accepted'
                    final_action = 'accept'
                else:
                    status_value = 'rejected'
                    final_action = 'reject'

                metadata = message.metadata or {}
                chatbot_response = metadata.get('chatbot_response', {})
                costing = chatbot_response.get('costing')
                if costing and isinstance(costing, dict) and 'data' in costing:
                    costing = costing['data']

                decision = {
                    'decision_id': f'chat-{message.message_id}',
                    'source': 'chat',
                    'question': message.content,
                    'status': status_value,
                    'final_action': final_action,
                    'values_before': {},
                    'values_after': {},
                    'values_after_proposed': costing or {},
                    'decided_at': decided_at,
                    'metadata': {
                        'message_id': message.message_id,
                        'session_id': message.session.session_id if message.session else None,
                        'conversation_id': message.conversation.conversation_id if message.conversation else None,
                    },
                }
                decisions.append(decision)

            # Attach decisions to versions based on timestamps
            version_numbers = sorted(version_timestamps.keys())
            timeline = [(vn, version_timestamps[vn]) for vn in version_numbers]

            for decision in decisions:
                ts = decision['decided_at']
                target_version = None

                if ts is None:
                    target_version = version_numbers[-1]
                else:
                    for vn, vts in timeline:
                        if ts <= vts:
                            target_version = vn
                            break
                    if target_version is None:
                        target_version = version_numbers[-1]

                idx = version_index_map.get(target_version)
                if idx is not None:
                    version_nodes[idx]['decisions'].append(decision)

            # Compute created_by_decisions for versions > 1
            for i, vn in enumerate(version_numbers):
                if i == 0:
                    continue

                current_ts = version_timestamps[vn]
                previous_vn = version_numbers[i - 1]
                previous_ts = version_timestamps[previous_vn]
                node_index = version_index_map.get(vn)
                if node_index is None:
                    continue

                created_ids = []
                for decision in decisions:
                    ts = decision['decided_at']
                    if ts is None:
                        continue
                    if ts > previous_ts and ts <= current_ts and decision['final_action'] == 'accept':
                        created_ids.append(decision['decision_id'])

                version_nodes[node_index]['created_from_version'] = previous_vn
                version_nodes[node_index]['created_by_decisions'] = created_ids

            response_payload = {
                'project_id': project.id,
                'project_key': self._build_project_key(project.name),
                'current_version': project.version_number,
                'versions': version_nodes,
            }

            response_serializer = ProjectDecisionGraphResponseSerializer(data=response_payload)
            if not response_serializer.is_valid():
                logger.error(f"Invalid decision graph data: {response_serializer.errors}")
                return Response({
                    'error': 'Invalid decision graph data',
                    'details': response_serializer.errors
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            logger.info(f"Successfully built decision graph for project {project_id} with {len(version_nodes)} versions")
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching project decision graph: {str(e)}", exc_info=True)
            return Response({
                'error': 'Internal server error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _build_base_data_for_version(self, project, version_number, historical=False, version_obj=None):
        """Build base_data structure (project + costs + overheads) for a specific version."""
        if historical and version_obj is not None:
            project_snapshot = {
                'name': version_obj.name,
                'location': version_obj.location,
                'total_cost': float(version_obj.total_cost) if version_obj.total_cost is not None else None,
                'start_date': version_obj.start_date,
                'end_date': version_obj.end_date,
            }

            version_costs = ProjectCostVersion.objects.filter(
                project=project,
                version_number=version_number
            ).order_by('id')

            cost_line_items = []
            for cost in version_costs:
                cost_line_items.append({
                    'id': cost.id,
                    'category_code': cost.category_code,
                    'category_name': cost.category_name,
                    'item_description': cost.item_description,
                    'supplier_brand': cost.supplier_brand,
                    'unit': cost.unit,
                    'quantity': float(cost.quantity) if cost.quantity is not None else None,
                    'rate_per_unit': float(cost.rate_per_unit) if cost.rate_per_unit is not None else None,
                    'line_total': float(cost.line_total) if cost.line_total is not None else None,
                    'category_total': float(cost.category_total) if cost.category_total is not None else None,
                })

            version_overheads = ProjectOverheadVersion.objects.filter(
                project=project,
                version_number=version_number
            ).order_by('id')

            overheads = []
            for overhead in version_overheads:
                overheads.append({
                    'id': overhead.id,
                    'overhead_type': overhead.overhead_type,
                    'basis': overhead.basis,
                    'description': overhead.description,
                    'percentage': float(overhead.percentage) if overhead.percentage is not None else None,
                    'amount': float(overhead.amount) if overhead.amount is not None else None,
                })

        else:
            project_snapshot = {
                'name': project.name,
                'location': project.location,
                'total_cost': float(project.total_cost) if project.total_cost is not None else None,
                'start_date': project.start_date,
                'end_date': project.end_date,
            }

            current_costs = ProjectCosts.objects.filter(project=project).order_by('id')
            cost_line_items = []
            for cost in current_costs:
                cost_line_items.append({
                    'id': cost.id,
                    'category_code': cost.category_code,
                    'category_name': cost.category_name,
                    'item_description': cost.item_description,
                    'supplier_brand': cost.supplier_brand,
                    'unit': cost.unit,
                    'quantity': float(cost.quantity) if cost.quantity is not None else None,
                    'rate_per_unit': float(cost.rate_per_unit) if cost.rate_per_unit is not None else None,
                    'line_total': float(cost.line_total) if cost.line_total is not None else None,
                    'category_total': float(cost.category_total) if cost.category_total is not None else None,
                })

            current_overheads = ProjectOverheads.objects.filter(project=project).order_by('id')
            overheads = []
            for overhead in current_overheads:
                overheads.append({
                    'id': overhead.id,
                    'overhead_type': overhead.overhead_type,
                    'basis': overhead.basis,
                    'description': overhead.description,
                    'percentage': float(overhead.percentage) if overhead.percentage is not None else None,
                    'amount': float(overhead.amount) if overhead.amount is not None else None,
                })

        return {
            'project': project_snapshot,
            'cost_line_items': cost_line_items,
            'overheads': overheads,
        }

    def _build_project_key(self, name):
        """Generate a stable project_key from the project name."""
        if not name:
            return 'PROJECT'
        key = ''.join(ch if ch.isalnum() else '_' for ch in name).upper()
        # Normalize multiple underscores
        parts = [p for p in key.split('_') if p]
        return '_'.join(parts) or 'PROJECT'

