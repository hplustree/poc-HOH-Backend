import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import requests
from datetime import datetime
from news.models import NewsArticle, NewsAPIResponse


class Command(BaseCommand):
    help = 'Fetch news from NewsData.io API and store in database'

    def handle(self, *args, **options):
        try:
            # API configuration
            api_url = os.environ.get("NEWS_API_URL")
            api_key = os.environ.get("NEWS_API_KEY")
            
            if not api_url:
                self.stdout.write(
                    self.style.ERROR('NEWS_API_URL environment variable is required')
                )
                return
            if not api_key:
                self.stdout.write(
                    self.style.ERROR('NEWS_API_KEY environment variable is required')
                )
                return
            
            # Query parameters
            params = {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate OR finance OR demographic',
                'country': 'in'
            }
            
            self.stdout.write('Fetching news from NewsData.io API...')
            
            # Make API request
            response = requests.get(api_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'success':
                self.stdout.write(
                    self.style.ERROR(f'API request failed: {data}')
                )
                return
            
            # Store API response metadata
            api_response = NewsAPIResponse.objects.create(
                status=data.get('status'),
                total_results=data.get('totalResults', 0),
                next_page=data.get('nextPage'),
                query_params=params
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'API Response stored with ID: {api_response.id}')
            )
            
            # Process and store articles
            articles_created = 0
            articles_updated = 0
            articles_skipped = 0
            
            for article_data in data.get('results', []):
                try:
                    # Skip articles with paid plan content
                    if (article_data.get('content') == 'ONLY AVAILABLE IN PAID PLANS' or
                        article_data.get('ai_summary') == 'ONLY AVAILABLE IN PAID PLANS'):
                        article_data['content'] = None
                    
                    # Parse publication date
                    pub_date_str = article_data.get('pubDate')
                    if pub_date_str:
                        pub_date = timezone.make_aware(datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S'))
                    else:
                        pub_date = timezone.now()
                    
                    # Create or update article
                    article, created = NewsArticle.objects.update_or_create(
                        article_id=article_data.get('article_id'),
                        defaults={
                            'title': article_data.get('title', ''),
                            'link': article_data.get('link', ''),
                            'description': article_data.get('description'),
                            'content': article_data.get('content'),
                            'pub_date': pub_date,
                            'pub_date_tz': article_data.get('pubDateTZ', 'UTC'),
                            'image_url': article_data.get('image_url'),
                            'video_url': article_data.get('video_url'),
                            'source_id': article_data.get('source_id', ''),
                            'source_name': article_data.get('source_name', ''),
                            'source_priority': article_data.get('source_priority'),
                            'source_url': article_data.get('source_url'),
                            'source_icon': article_data.get('source_icon'),
                            'language': article_data.get('language', 'english'),
                            'country': article_data.get('country', []),
                            'category': article_data.get('category', []),
                            'keywords': article_data.get('keywords', []),
                            'creator': article_data.get('creator', []),
                            'duplicate': article_data.get('duplicate', False),
                        }
                    )
                    
                    if created:
                        articles_created += 1
                        self.stdout.write(f'Created: {article.title[:50]}...')
                    else:
                        articles_updated += 1
                        self.stdout.write(f'Updated: {article.title[:50]}...')
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Error processing article {article_data.get("article_id")}: {str(e)}')
                    )
                    articles_skipped += 1
                    continue
            
            # Summary
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nNews fetch completed successfully!\n'
                    f'Total results from API: {data.get("totalResults", 0)}\n'
                    f'Articles processed: {len(data.get("results", []))}\n'
                    f'Articles created: {articles_created}\n'
                    f'Articles updated: {articles_updated}\n'
                    f'Articles skipped: {articles_skipped}'
                )
            )
            
        except requests.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to fetch news from API: {str(e)}')
            )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Internal error: {str(e)}')
            )
