from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from .models import UserDetail
from .serializers import (
    UserDetailRegistrationSerializer, UserDetailLoginSerializer, 
    OTPVerificationSerializer, UserDetailSerializer
)

# UserDetail Registration with OTP
@api_view(['POST'])
@permission_classes([AllowAny])
def user_detail_register_view(request):
    serializer = UserDetailRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user_detail = serializer.save()
        # TODO: Send OTP via email/SMS service instead of returning it
        # TEMPORARY: Return OTP for testing (remove in production)
        return Response({
            'message': 'User registered successfully. OTP sent for verification.',
            'user': UserDetailSerializer(user_detail).data,
            'otp': user_detail.otp,  # For testing only
            'otp_expires_in': '80 seconds'
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_view(request):
    serializer = OTPVerificationSerializer(data=request.data)
    if serializer.is_valid():
        user_detail = serializer.validated_data['user_detail']
        return Response({
            'message': 'OTP verified successfully. Account activated.',
            'user': UserDetailSerializer(user_detail).data
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def user_detail_login_view(request):
    serializer = UserDetailLoginSerializer(data=request.data)
    if serializer.is_valid():
        user_detail = serializer.validated_data['user_detail']
        # Create a dummy user for JWT token generation
        try:
            user = User.objects.get(email=user_detail.email)
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=user_detail.email,
                email=user_detail.email,
                first_name=user_detail.first_name,
                last_name=user_detail.last_name
            )
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Login successful',
            'user': UserDetailSerializer(user_detail).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def resend_otp_view(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user_detail = UserDetail.objects.get(email=email)
        if user_detail.is_verified:
            return Response({'error': 'Account already verified'}, status=status.HTTP_400_BAD_REQUEST)
        
        otp = user_detail.generate_otp()
        user_detail.save()
        
        # TODO: Send OTP via email/SMS service instead of returning it
        return Response({
            'message': 'New OTP generated successfully',
            'otp_expires_in': '80 seconds'
        }, status=status.HTTP_200_OK)
    except UserDetail.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Invalid token'
        }, status=status.HTTP_400_BAD_REQUEST)
