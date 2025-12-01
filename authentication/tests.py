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

    def test_user_registration_with_multiple_projects(self):
        """Test that new user gets sessions for all existing projects"""
        from budget.models import Projects
        from chatapp.models import Session, Conversation, Messages
        
        # Create 3 test projects
        project1 = Projects.objects.create(
            name='Test Project 1',
            location='Location 1',
            total_cost=10000
        )
        project2 = Projects.objects.create(
            name='Test Project 2',
            location='Location 2',
            total_cost=20000
        )
        project3 = Projects.objects.create(
            name='Test Project 3',
            location='Location 3',
            total_cost=30000
        )
        
        # Register new user
        response = self.client.post('/api/auth/register/', self.user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify response contains chat_setup statistics
        self.assertIn('chat_setup', response.data)
        chat_setup = response.data['chat_setup']
        
        # Verify sessions were created for all 3 projects
        self.assertTrue(chat_setup.get('success'))
        self.assertEqual(chat_setup.get('projects_processed'), 3)
        self.assertEqual(chat_setup.get('sessions_created'), 3)
        self.assertEqual(chat_setup.get('conversations_created'), 3)
        self.assertEqual(chat_setup.get('messages_created'), 3)
        
        # Verify in database
        user_detail = UserDetail.objects.get(email=self.user_data['email'])
        sessions = Session.objects.filter(user_id=user_detail)
        self.assertEqual(sessions.count(), 3)
        
        # Verify each session has a conversation and welcome message
        for session in sessions:
            conversations = Conversation.objects.filter(session=session)
            self.assertEqual(conversations.count(), 1)
            
            messages = Messages.objects.filter(session=session, message_type='assistant')
            self.assertEqual(messages.count(), 1)
            self.assertIn('Welcome to', messages.first().content)

    def test_user_registration_with_no_projects(self):
        """Test that user registration works even when no projects exist"""
        # Make sure no projects exist
        from budget.models import Projects
        Projects.objects.all().delete()
        
        # Register new user
        response = self.client.post('/api/auth/register/', self.user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify response contains chat_setup with no sessions created
        self.assertIn('chat_setup', response.data)
        chat_setup = response.data['chat_setup']
        self.assertTrue(chat_setup.get('success'))
        self.assertFalse(chat_setup.get('projects_exist'))
        self.assertEqual(chat_setup.get('sessions_created'), 0)
