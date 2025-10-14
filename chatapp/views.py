from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from .models import Session, Conversation, Messages, UpdatedCost
from .serializers import (
    SessionSerializer, ConversationSerializer, MessageSerializer, 
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
    Handle user message: save to DB and send to external API
    """
    try:
        serializer = MessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
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
                conversation = Conversation.objects.create(session=session)
                conversation_id = conversation.conversation_id
            
            # Save user message to database
            user_message = save_message_to_db(
                conversation_id=conversation_id,
                sender_id=user_detail.id if user_detail else None,
                message_type=message_type,
                content=content
            )
            
            # Build payload for external API
            api_payload = build_api_payload(
                question=content,
                session_id=session_id,
                conversation_id=conversation_id
            )
            
            # Send to external chatbot API
            api_response = send_to_external_api(api_payload)
            
            response_data = {
                'success': True,
                'message_saved': True,
                'user_message': MessageSerializer(user_message).data,
                'conversation_id': conversation_id,
                'api_payload_sent': api_payload,
                'external_api_response': api_response
            }
            
            # If external API was successful, save AI response and costing data
            if api_response.get('success') and 'data' in api_response:
                chatbot_response = api_response['data']
                
                # Extract answer and costing from chatbot response
                ai_answer = chatbot_response.get('answer', 'No response from chatbot')
                costing_data = chatbot_response.get('costing', {})
                
                # Save AI message with the answer
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
                
                # Save costing data to UpdatedCost table if present
                if costing_data and costing_data.get('status') == 'success':
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
