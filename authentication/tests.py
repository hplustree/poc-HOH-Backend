from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from .models import UserDetail

class UserDetailTestCase(APITestCase):
    def setUp(self):
        self.user_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123'
        }

    def test_user_registration(self):
        """Test user registration with OTP generation"""
        response = self.client.post('/api/auth/register/', self.user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(UserDetail.objects.filter(email=self.user_data['email']).exists())

    def test_duplicate_email_registration(self):
        """Test that duplicate email registration fails"""
        UserDetail.objects.create(
            first_name='Jane',
            last_name='Doe',
            email=self.user_data['email']
        )
        response = self.client.post('/api/auth/register/', self.user_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
