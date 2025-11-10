from rest_framework import serializers
from .models import UserDetail

class UserDetailRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = UserDetail
        fields = ('first_name', 'last_name', 'email', 'password', 'password_confirm')

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def validate_email(self, value):
        if UserDetail.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Create user detail instance
        user_detail = UserDetail(**validated_data)
        user_detail.set_password(password)
        
        # Generate OTP (user remains inactive until OTP verification)
        otp = user_detail.generate_otp()
        user_detail.save()
        
        return user_detail

class UserDetailLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            try:
                user_detail = UserDetail.objects.get(email=email)
                if not user_detail.check_password(password):
                    raise serializers.ValidationError('Invalid credentials.')
                if not user_detail.is_verified:
                    raise serializers.ValidationError('Account not verified. Please verify with OTP.')
                attrs['user_detail'] = user_detail
                return attrs
            except UserDetail.DoesNotExist:
                raise serializers.ValidationError('Invalid credentials.')
        else:
            raise serializers.ValidationError('Must include email and password.')

class OTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')

        try:
            user_detail = UserDetail.objects.get(email=email)
            if not user_detail.verify_otp(otp):
                raise serializers.ValidationError('Invalid or expired OTP.')
            attrs['user_detail'] = user_detail
            return attrs
        except UserDetail.DoesNotExist:
            raise serializers.ValidationError('User not found.')

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDetail
        fields = ('id', 'first_name', 'last_name', 'email', 'is_verified', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'is_verified', 'is_active', 'created_at', 'updated_at')

