from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from datetime import timedelta
import random
import string

class UserDetail(models.Model):
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_details'
        verbose_name = 'User Detail'
        verbose_name_plural = 'User Details'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def set_password(self, raw_password):
        """Hash and set the password"""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Check if the provided password matches the stored password"""
        return check_password(raw_password, self.password)

    def generate_otp(self):
        """Generate a 6-digit OTP and set expiry time"""
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = timezone.now()
        return self.otp

    def is_otp_valid(self):
        """Check if OTP is still valid (within 80 seconds)"""
        if not self.otp or not self.otp_created_at:
            return False
        
        expiry_time = self.otp_created_at + timedelta(seconds=80)
        return timezone.now() <= expiry_time

    def clear_expired_otp(self):
        """Clear OTP if it has expired"""
        if not self.is_otp_valid():
            self.otp = None
            self.otp_created_at = None
            self.save()

    def verify_otp(self, provided_otp):
        """Verify the provided OTP and activate user"""
        if not self.is_otp_valid(): 
            self.clear_expired_otp()
            return False
        
        if self.otp == provided_otp:
            self.is_verified = True
            self.is_active = True  # Activate user only after OTP verification
            self.otp = None
            self.otp_created_at = None
            self.save()
            return True
        
        return False
