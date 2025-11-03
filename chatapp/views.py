from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import generics
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Session, Conversation, Messages, UpdatedCost
from .serializers import (
    SessionSerializer, ConversationSerializer, ConversationCreateSerializer, MessageSerializer, 
    MessageCreateSerializer, UpdatedCostSerializer, UpdatedCostStatusSerializer
)
from .utils import build_api_payload, send_to_external_api, save_message_to_db, save_updated_cost_to_db
from authentication.models import UserDetail


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session(request):
    """
    Create a new chat session for a project
    """
    try:
        project_id = request.data.get('project_id')
        user_email = request.user.email if hasattr(request.user, 'email') else request.data.get('user_email')
        
        # Get user from UserDetail model
        try:
            user_detail = UserDetail.objects.get(email=user_email)
        except UserDetail.DoesNotExist:
            return Response({
                'error': 'User not found in system'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create session
        session_data = {
            'project_id': project_id,
            'user_id': user_detail.id,
            'is_active': True
        }
        
        serializer = SessionSerializer(data=session_data)
        if serializer.is_valid():
            session = serializer.save()
            return Response({
                'success': True,
                'session': SessionSerializer(session).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'Failed to create session',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request):
    """
    Handle user message: save to DB first, then call external chatbot API with complete payload
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.debug(f"Incoming request - Method: {request.method}, Content-Type: {request.content_type}")
    
    try:
        serializer = MessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation errors: {serializer.errors}")
            return Response({
                'success': False,
                'error': 'Invalid data',
                'details': serializer.errors,
                'required_fields': ['session_id', 'content'],
                'optional_fields': ['conversation_id', 'message_type']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session_id = serializer.validated_data['session_id']
        conversation_id = serializer.validated_data.get('conversation_id')
        content = serializer.validated_data['content']
        message_type = serializer.validated_data['message_type']
        
        # Get user from UserDetail model
        user_email = request.user.email if hasattr(request.user, 'email') else None
        user_detail = None
        if user_email:
            try:
                user_detail = UserDetail.objects.get(email=user_email)
            except UserDetail.DoesNotExist:
                pass
        
        with transaction.atomic():
            # Get or create conversation
            if conversation_id:
                try:
                    conversation = Conversation.objects.get(conversation_id=conversation_id)
                except Conversation.DoesNotExist:
                    return Response({
                        'error': 'Conversation not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                # Create new conversation
                session = Session.objects.get(session_id=session_id)
                conversation = Conversation.objects.create(
                    session=session,
                    project_id=session.project_id  # Use project_id from session
                )
                conversation_id = conversation.conversation_id
            
            # STEP 1: Save user message to database FIRST
            user_message = save_message_to_db(
                conversation_id=conversation_id,
                sender_id=user_detail.id if user_detail else None,
                message_type=message_type,
                content=content
            )
            
            # STEP 2: Build complete payload for external API
            # This includes: latest project costing, last 10 chats, accepted decisions
            api_payload = build_api_payload(
                question=content,
                session_id=session_id,
                conversation_id=conversation_id
            )
            
            # STEP 3: Send to external chatbot API
            api_response = send_to_external_api(api_payload)
            
            response_data = {
                'success': True,
                'message_saved': True,
                'user_message': MessageSerializer(user_message).data,
                'conversation_id': conversation_id,
                'api_payload_sent': api_payload,
                'external_api_response': api_response
            }
            
            # STEP 4: Process API response and save chatbot answer
            if api_response.get('success') and 'data' in api_response:
                chatbot_response = api_response['data']
                
                # Extract answer from chatbot response
                ai_answer = chatbot_response.get('answer', 'I apologize, but that information is not available in this project documentation. I can only assist with questions related to this construction project.')
                costing_data = chatbot_response.get('costing', None)
                
                # STEP 5: Save AI message with the answer to chat
                ai_message = save_message_to_db(
                    conversation_id=conversation_id,
                    sender_id=None,  # AI message has no sender
                    message_type='assistant',
                    content=ai_answer,
                    metadata={
                        'chatbot_response': chatbot_response,
                        'has_costing_update': bool(costing_data)
                    }
                )
                
                response_data['ai_message'] = MessageSerializer(ai_message).data
                response_data['chatbot_answer'] = ai_answer
                
                # STEP 6: Save costing data if present
                if costing_data and isinstance(costing_data, dict) and costing_data.get('status') == 'success':
                    try:
                        updated_cost = save_updated_cost_to_db(
                            conversation_id=conversation_id,
                            message_id=ai_message.message_id,
                            costing_data=costing_data,
                            raw_response=chatbot_response
                        )
                        
                        response_data['updated_cost_saved'] = True
                        response_data['updated_cost_id'] = updated_cost.updated_cost_id
                        response_data['costing_data'] = costing_data
                        
                    except Exception as e:
                        response_data['updated_cost_error'] = f'Failed to save costing data: {str(e)}'
                        response_data['updated_cost_saved'] = False
                else:
                    response_data['updated_cost_saved'] = False
                    response_data['costing_data'] = None
            else:
                # Handle API failure - still save a default response
                error_message = "I apologize, but I'm currently unable to process your request. Please try again later."
                
                ai_message = save_message_to_db(
                    conversation_id=conversation_id,
                    sender_id=None,
                    message_type='assistant',
                    content=error_message,
                    metadata={
                        'api_error': True,
                        'api_response': api_response
                    }
                )
                
                response_data['ai_message'] = MessageSerializer(ai_message).data
                response_data['chatbot_answer'] = error_message
                response_data['updated_cost_saved'] = False
                response_data['costing_data'] = None
            
            return Response(response_data, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': 'Failed to process message',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conversation_history(request, conversation_id):
    """
    Get all messages in a conversation
    """
    try:
        conversation = Conversation.objects.get(conversation_id=conversation_id)
        messages = Messages.objects.filter(conversation=conversation).order_by('created_at')
        
        serializer = MessageSerializer(messages, many=True)
        
        return Response({
            'success': True,
            'conversation_id': conversation_id,
            'messages': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Conversation.DoesNotExist:
        return Response({
            'error': 'Conversation not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to get conversation history',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_sessions(request):
    """
    Get all sessions for the current user
    """
    try:
        user_email = request.user.email if hasattr(request.user, 'email') else request.GET.get('user_email')
        
        if not user_email:
            return Response({
                'error': 'User email required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_detail = UserDetail.objects.get(email=user_email)
        except UserDetail.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        sessions = Session.objects.filter(user_id=user_detail).order_by('-updated_at')
        serializer = SessionSerializer(sessions, many=True)
        
        return Response({
            'success': True,
            'sessions': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to get user sessions',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_updated_costs(request):
    """
    Get updated costs with optional filtering
    """
    try:
        # Query parameters for filtering
        conversation_id = request.GET.get('conversation_id')
        is_accept = request.GET.get('is_accept')
        limit = int(request.GET.get('limit', 20))
        
        # Build query
        queryset = UpdatedCost.objects.all()
        
        if conversation_id:
            queryset = queryset.filter(conversation__conversation_id=conversation_id)
        if is_accept is not None:
            if is_accept.lower() == 'true':
                queryset = queryset.filter(is_accept=True)
            elif is_accept.lower() == 'false':
                queryset = queryset.filter(is_accept=False)
            elif is_accept.lower() == 'null':
                queryset = queryset.filter(is_accept__isnull=True)
        
        # Limit results and order by most recent
        updated_costs = queryset.order_by('-created_at')[:limit]
        
        # Serialize data
        serializer = UpdatedCostSerializer(updated_costs, many=True)
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'updated_costs': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve updated costs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_updated_cost_detail(request, updated_cost_id):
    """
    Get detailed information about a specific updated cost
    """
    try:
        updated_cost = UpdatedCost.objects.get(updated_cost_id=updated_cost_id)
        serializer = UpdatedCostSerializer(updated_cost)
        
        return Response({
            'success': True,
            'updated_cost': serializer.data
        }, status=status.HTTP_200_OK)
        
    except UpdatedCost.DoesNotExist:
        return Response({
            'error': 'Updated cost not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to get updated cost details',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_cost_status(request, updated_cost_id):
    """
    Update the is_accept status of a specific updated cost
    
    Expected payload:
    {
        "is_accept": true/false/null
    }
    """
    try:
        updated_cost = UpdatedCost.objects.get(updated_cost_id=updated_cost_id)
        
        # Validate the request data
        serializer = UpdatedCostStatusSerializer(updated_cost, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_record = serializer.save()
            
            # Return updated cost data
            response_serializer = UpdatedCostSerializer(updated_record)
            
            return Response({
                'success': True,
                'message': f'Updated cost {updated_cost_id} status updated successfully',
                'updated_cost': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        else:
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except UpdatedCost.DoesNotExist:
        return Response({
            'error': 'Updated cost not found',
            'message': f'Updated cost with ID {updated_cost_id} does not exist'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        return Response({
            'error': 'Failed to update cost status',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SessionListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating chat sessions
    """
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Return only active sessions for the authenticated user
        user_email = self.request.user.email
        return Session.objects.filter(
            user_id__email=user_email,
            is_active=True
        ).select_related('project_id', 'user_id').order_by('-created_at')

    def perform_create(self, serializer):
        # Get user from UserDetail model
        user_email = self.request.user.email
        user_detail = get_object_or_404(UserDetail, email=user_email)
        
        # Set the user and ensure the session is active
        serializer.save(
            user_id=user_detail,
            is_active=True
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_conversations(request):
    """
    Get all conversations for the authenticated user
    """
    try:
        user_email = request.user.email
        
        # Get all conversations for the user's sessions
        conversations = Conversation.objects.filter(
            session__user_id__email=user_email,
            session__is_active=True
        ).select_related(
            'session', 
            'session__project_id', 
            'session__user_id'
        ).order_by('-conversation_id')
        
        serialized_conversations = ConversationSerializer(conversations, many=True).data
        
        return Response({
            'success': True,
            'count': len(serialized_conversations),
            'conversations': serialized_conversations
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve conversations',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_conversation(request):
    """
    Create a new conversation within a session
    """
    try:
        serializer = ConversationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Invalid data',
                'details': serializer.errors,
                'required_fields': ['session_id', 'project_id']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify the session belongs to the authenticated user
        session_id = serializer.validated_data['session_id']
        project_id = serializer.validated_data['project_id']
        user_email = request.user.email
        
        try:
            session = Session.objects.get(
                session_id=session_id,
                user_id__email=user_email,
                is_active=True
            )
        except Session.DoesNotExist:
            return Response({
                'error': 'Session not found or you do not have permission to access it'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Validate that project_id matches the session's project
        if project_id != session.project_id.id:
            return Response({
                'error': 'Project ID does not match the session\'s project',
                'session_project_id': session.project_id.id,
                'provided_project_id': project_id
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the conversation
        conversation = serializer.save()
        
        # Return the created conversation with full details
        conversation_data = ConversationSerializer(conversation).data
        
        return Response({
            'success': True,
            'message': 'Conversation created successfully',
            'conversation': conversation_data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': 'Failed to create conversation',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_chats(request):
    """
    Get chat messages for a specific conversation
    """
    try:
        conversation_id = request.GET.get('conversation_id')
        
        if not conversation_id:
            return Response({
                'error': 'conversation_id parameter is required',
                'message': 'Please provide conversation_id in query parameters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Fetch conversation with related session and project data
        try:
            conversation = Conversation.objects.select_related(
                'session', 
                'session__project_id'
            ).get(conversation_id=conversation_id)
        except Conversation.DoesNotExist:
            return Response({
                'error': 'Conversation not found',
                'message': f'No conversation found with ID {conversation_id}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Fetch all messages for this conversation in chronological order
        messages = Messages.objects.filter(
            conversation=conversation
        ).order_by('created_at')
        
        # Serialize messages using the existing serializer
        serialized_messages = MessageSerializer(messages, many=True).data
        
        # Build comprehensive response
        response_data = {
            'success': True,
            'conversation': {
                'conversation_id': conversation.conversation_id,
                'session_id': conversation.session.session_id,
                'project': {
                    'project_id': conversation.session.project_id.id if conversation.session.project_id else None,
                    'project_name': conversation.session.project_id.name if conversation.session.project_id else None,
                    'location': conversation.session.project_id.location if conversation.session.project_id else None
                },
                'session_timestamps': {
                    'created_at': conversation.session.created_at,
                    'updated_at': conversation.session.updated_at
                },
                'message_count': len(serialized_messages),
                'messages': serialized_messages
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid conversation_id',
            'message': 'conversation_id must be a valid integer',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve chat messages',
            'message': 'An unexpected error occurred while fetching the conversation',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_conversation(request, conversation_id):
    """
    Delete a conversation and all related data (messages, updated_costs)
    Only the owner of the conversation can delete it
    """
    try:
        user_email = request.user.email
        
        # Get conversation with related data for verification
        try:
            conversation = Conversation.objects.select_related(
                'session', 
                'session__user_id',
                'project_id'
            ).get(conversation_id=conversation_id)
        except Conversation.DoesNotExist:
            return Response({
                'error': 'Conversation not found',
                'message': f'No conversation found with ID {conversation_id}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify ownership - only the user who owns the session can delete
        if conversation.session.user_id.email != user_email:
            return Response({
                'error': 'Permission denied',
                'message': 'You can only delete your own conversations'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get counts before deletion for response
        message_count = conversation.messages.count()
        updated_cost_count = conversation.updated_costs.count()
        
        # Store conversation info for response
        conversation_info = {
            'conversation_id': conversation.conversation_id,
            'project_name': conversation.project_id.name,
            'session_id': conversation.session.session_id,
            'message_count': message_count,
            'updated_cost_count': updated_cost_count
        }
        
        # Delete conversation (CASCADE will handle related objects)
        with transaction.atomic():
            conversation.delete()
        
        return Response({
            'success': True,
            'message': 'Conversation deleted successfully',
            'deleted_conversation': conversation_info,
            'cascade_deletions': {
                'messages_deleted': message_count,
                'updated_costs_deleted': updated_cost_count
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to delete conversation',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
