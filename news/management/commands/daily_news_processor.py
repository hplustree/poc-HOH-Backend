import os
import json
import requests
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from news.models import NewsArticle, Alert
from budget.models import Projects
from chatapp.utils import generate_costing_json_from_db
from dotenv import load_dotenv

load_dotenv()
class Command(BaseCommand):
    help = 'Daily cron job to fetch news and send to decision API - runs at 3 AM daily'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
            ]
        )
        self.logger = logging.getLogger(__name__)

    def handle(self, *args, **options):
        """
        Main handler for the daily news processing cron job.
        1. Calls the news fetch endpoint    
        2. Gets latest news from database
        3. Sends to decision API 
        """
        start_time = timezone.now()
        self.log_separator('DAILY NEWS PROCESSING STARTED')
        print(f'Starting daily news processing at {start_time}')
        
        try:
            # Step 1: Fetch news from the endpoint
            self.log_step(1, "Fetching news from external API")
            self.fetch_news_from_endpoint()
            
            # Step 2: Get latest news from database
            self.log_step(2, "Retrieving latest news from database")
            latest_news = self.get_latest_news()
            
            if not latest_news:
                print('WARNING: No news articles found in database')
                return
            
            # Step 3: Send to decision API
            self.log_step(3, "Sending news to decision API")
            self.send_to_decision_api(latest_news)
            
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            print(f'Daily news processing completed successfully!')
            print(f'Total execution time: {duration:.2f} seconds')
            self.log_separator('DAILY NEWS PROCESSING COMPLETED')
            
        except Exception as e:
            print(f'ERROR: Error in daily news processing: {str(e)}')
            self.logger.error(f'Daily news processing failed: {str(e)}', exc_info=True)
            self.log_separator('DAILY NEWS PROCESSING FAILED')

    def log_separator(self, message):
        """Print a separator line with message"""
        separator = "=" * 60
        print(f'\n{separator}')
        print(f'{message.center(60)}')
        print(f'{separator}\n')

    def log_step(self, step_num, description):
        """Log a processing step"""
        print(f'\nSTEP {step_num}: {description}')
        print('-' * 50)

    def fetch_news_from_endpoint(self):
        try:
            print('Calling news fetch API...')
            
            # Use the exact URL from the curl command
            url = os.getenv('BASE_URI') + '/api/news/fetch/'
            headers = {
                'Content-Type': 'application/json'
            }
            
            print(f'URL: {url}')
            print(f'Headers: {headers}')
            
            response = requests.post(url, headers=headers, timeout=120)
            response.raise_for_status()
            
            print(f'News fetch successful!')
            print(f'Status Code: {response.status_code}')
            
            # Log response details
            if response.text:
                try:
                    response_data = response.json()
                    print(f'Response Data: {json.dumps(response_data, indent=2)[:500]}...')
                except json.JSONDecodeError:
                    print(f'Response Text: {response.text[:500]}...')
            
            self.logger.info(f'News fetch API call successful - Status: {response.status_code}')
                
        except requests.RequestException as e:
            error_msg = f'Failed to fetch news from endpoint: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f'Unexpected error in news fetching: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)
            raise

    def get_latest_news(self):
        """
        Retrieves the latest news articles from the database
        """
        try:
            print('Querying database for latest news...')
            
            # Get latest news articles ordered by publication date
            articles = NewsArticle.objects.order_by('-pub_date')[:20]  # Get configurable number of articles
            print(articles)
            news_list = []
            for article in articles:
                news_item = {
                    "article_id": article.article_id,
                    "title": article.title,
                    "link": article.link,
                    "description": article.description or "",
                    "content": article.content,
                    "pub_date": article.pub_date.isoformat() if article.pub_date else None,
                    "pub_date_tz": article.pub_date_tz,
                    "image_url": article.image_url,
                    "video_url": article.video_url,
                    "source_id": article.source_id,
                    "source_name": article.source_name,
                    "source_icon": article.source_icon,
                    "language": article.language,
                    "country": article.country,
                    "category": article.category,
                    "keywords": article.keywords,
                    "creator": article.creator,
                    "created_at": article.created_at.isoformat() if article.created_at else None
                }
                news_list.append(news_item)
            
            print(f'Retrieved {len(news_list)} news articles from database')
            
            # Log sample articles
            if news_list:
                print('Sample articles:')
                for i, article in enumerate(news_list[:3]):
                    print(f'  {i+1}. {article["title"][:80]}...')
            
            self.logger.info(f'Retrieved {len(news_list)} articles from database')
            return news_list
            
        except Exception as e:
            error_msg = f'Error retrieving news from database: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)
            raise

    def send_to_decision_api(self, news_list):
        try:
            print('Sending news to decision API...')
            
            # Fetch all active (non-deleted) projects
            projects = Projects.objects.filter(is_delete=False).order_by('-updated_at')
            if not projects.exists():
                print('WARNING: No active projects found. Skipping decision API calls.')
                return

            # Use the exact URL from the curl command
            url = os.getenv('ML_BASE_URI') + '/api/news_decision'

            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }

            print(f'URL: {url}')
            print(f'Headers: {headers}')
            print(f'Total articles to send: {len(news_list)}')
            print(f'Total projects to process: {projects.count()}')

            # Send news + costing for each project one by one
            for project in projects:
                try:
                    print('\n' + '-' * 60)
                    print(f'Processing project ID {project.id} (project_id={getattr(project, "project_id", "")})')

                    # Prepare project identifiers
                    project_uuid = str(getattr(project, 'project_id', '') or '')
                    version_id = str(project.version_number) if getattr(project, 'version_number', None) is not None else ""

                    # Generate costing_json for this project
                    costing_json = generate_costing_json_from_db(project_id=project.id, include_wrapper=False)

                    # Fallback if costing_json generator returned an error structure
                    if isinstance(costing_json, dict) and costing_json.get("status") == "error":
                        print(f'WARNING: Error in costing_json for project {project.id}: {costing_json.get("message")}')
                        costing_json = {}

                    # Prepare the payload exactly as specified in the curl command
                    payload = {
                        "project_id": project_uuid,
                        "version_id": version_id,
                        "news": {
                            "success": True,
                            "count": len(news_list),
                            "results": news_list
                        },
                        "costing_json": costing_json,
                    }

                    print(f'Sending payload for project_id={project_uuid}, version_id={version_id}')

                    response = requests.post(
                        url,
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=120
                    )
                    response.raise_for_status()

                    print(f'Decision API call successful for project_id={project_uuid}!')
                    print(f'Status Code: {response.status_code}')

                    # Log the complete response as requested
                    print('\n' + '='*60)
                    print('DECISION API RESPONSE LOG')
                    print('='*60)

                    # Log response headers
                    print(f'Response Headers: {dict(response.headers)}')
                    print(f'Response Status: {response.status_code}')
                    print(f'Response Time: {response.elapsed.total_seconds():.2f} seconds')
                    print('-' * 60)

                    try:
                        response_json = response.json()
                        formatted_response = json.dumps(response_json, indent=2)
                        print('Response Body (JSON):')
                        print(formatted_response)

                        # Save alerts to database with project reference
                        self.save_alerts_to_database(response_json, project)

                        # Log to file as well
                        self.logger.info(f'Decision API call successful for project_id={project_uuid} - Status: {response.status_code}')
                        self.logger.info(f'Decision API response headers: {dict(response.headers)}')
                        self.logger.info(f'Decision API response time: {response.elapsed.total_seconds():.2f}s')
                        self.logger.info(f'Decision API response body: {formatted_response}')

                    except json.JSONDecodeError:
                        print('Response Body (Text):')
                        print(response.text)

                        # Log to file as well
                        self.logger.info(f'Decision API call successful for project_id={project_uuid} - Status: {response.status_code}')
                        self.logger.info(f'Decision API response headers: {dict(response.headers)}')
                        self.logger.info(f'Decision API response time: {response.elapsed.total_seconds():.2f}s')
                        self.logger.info(f'Decision API response body (text): {response.text}')

                    print('='*60)
                    print('END DECISION API RESPONSE LOG')
                    print('='*60 + '\n')

                except requests.RequestException as e:
                    error_msg = f'Failed to send news to decision API for project_id={getattr(project, "project_id", "")}: {str(e)}'
                    print(f'ERROR: {error_msg}')
                    self.logger.error(error_msg)
                    # Continue with next project instead of raising
                    continue
                except Exception as e:
                    error_msg = f'Unexpected error in decision API call for project_id={getattr(project, "project_id", "")}: {str(e)}'
                    print(f'ERROR: {error_msg}')
                    self.logger.error(error_msg)
                    # Continue with next project
                    continue
            
        except requests.RequestException as e:
            error_msg = f'Failed to send news to decision API: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f'Unexpected error in decision API call: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)
            raise

    def save_alerts_to_database(self, response_data, project):
        """
        Save decision API response alerts to the database
        """
        try:
            print(f'Saving alerts to database for project_id={getattr(project, "project_id", "")}...')
            
            if 'response' not in response_data:
                print('WARNING: No response data found to save')
                return
            
            alerts_saved = 0
            response_dict = response_data['response']
            
            for decision_key, alert_data in response_dict.items():
                try:
                    # Extract updated costing data if available
                    updated_costing = alert_data.get('updated_costing', {})
                    old_values = updated_costing.get('old_values', {})
                    new_values = updated_costing.get('new_values', {})
                    
                    # Create Alert object and link to this project
                    alert = Alert.objects.create(
                        project_id=project,
                        decision_key=decision_key,
                        decision=alert_data.get('decision', ''),
                        reason=alert_data.get('reason', ''),
                        suggestion=alert_data.get('suggestion', ''),
                        
                        # Updated costing information
                        category_name=updated_costing.get('category_name'),
                        item=updated_costing.get('item'),
                        unit=updated_costing.get('unit'),
                        quantity=updated_costing.get('quantity'),
                        
                        # Old values
                        old_supplier_brand=old_values.get('supplier_brand'),
                        old_rate_per_unit=old_values.get('rate_per_unit'),
                        old_line_total=old_values.get('line_total'),
                        
                        # New values
                        new_supplier_brand=new_values.get('supplier_brand'),
                        new_rate_per_unit=new_values.get('rate_per_unit'),
                        new_line_total=new_values.get('line_total'),
                        
                        # Impact details
                        cost_impact=updated_costing.get('cost_impact'),
                        impact_reason=updated_costing.get('impact_reason'),
                        
                        # Raw response for backup
                        raw_response=alert_data
                    )
                    
                    alerts_saved += 1
                    print(f'Saved alert {alert.alert_id}: {alert.decision[:50]}...')
                    
                except Exception as e:
                    print(f'ERROR: Error saving alert for key {decision_key}: {str(e)}')
                    self.logger.error(f'Error saving alert for key {decision_key}: {str(e)}')
            
            print(f'Successfully saved {alerts_saved} alerts to database')
            self.logger.info(f'Saved {alerts_saved} alerts to database')
            
        except Exception as e:
            error_msg = f'Error saving alerts to database: {str(e)}'
            print(f'ERROR: {error_msg}')
            self.logger.error(error_msg)

    def add_arguments(self, parser):
        """
        Add command line arguments
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making actual API calls (for testing)',
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Run in test mode with detailed logging',
        )
