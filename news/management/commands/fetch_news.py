# This command has been replaced by daily_news_processor.py
# Use: python manage.py daily_news_processor instead

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'DEPRECATED: Use daily_news_processor instead'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                'WARNING: This command is DEPRECATED!\n'
                'Use: python manage.py daily_news_processor\n'
                'The daily_news_processor command handles both news fetching and processing.'
            )
        )
