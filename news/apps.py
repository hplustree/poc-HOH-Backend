import sys
from django.apps import AppConfig
from django.core.management import call_command


class NewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news'

    def ready(self):
        """
        Called when Django starts up - automatically setup cron job when running server
        """
        # Only setup cron job when running the server
        if 'runserver' in sys.argv:
            try:
                print("Auto-setting up cron job...")
                call_command('setup_cron')
                print("Cron job setup completed!")
            except Exception as e:
                print(f"Warning: Could not setup cron job automatically: {e}")
                print("You can manually run: python manage.py setup_cron")
