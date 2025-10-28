from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Projects
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Projects)
def create_sessions_for_new_project(sender, instance, created, **kwargs):
    """
    Signal handler to create sessions and conversations for all users when a new project is created
    """
    if created:  # Only run for newly created projects
        try:
            # Import here to avoid circular imports
            from chatapp.utils import create_sessions_for_all_users_on_project_creation
            
            logger.info(f"New project created: {instance.name} (ID: {instance.id})")
            
            # Create sessions and conversations for all existing users
            result = create_sessions_for_all_users_on_project_creation(instance)
            
            if result['success']:
                logger.info(
                    f"Successfully created sessions for project '{instance.name}': "
                    f"{result['sessions_created']} sessions, "
                    f"{result['conversations_created']} conversations for "
                    f"{result['users_processed']} users"
                )
                
                if result['errors']:
                    logger.warning(
                        f"Some errors occurred while creating sessions for project '{instance.name}': "
                        f"{result['errors']}"
                    )
            else:
                logger.error(
                    f"Failed to create sessions for project '{instance.name}': "
                    f"{result['error']}"
                )
                
        except Exception as e:
            logger.error(
                f"Error in create_sessions_for_new_project signal for project '{instance.name}': {str(e)}"
            )
