import os
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, serializers
from .models import NewsArticle, NewsAPIResponse, Alert
from .serializers import AlertSerializer, AlertStatusUpdateSerializer
from dotenv import load_dotenv
load_dotenv()
class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = [
            'article_id', 'title', 'link', 'description', 'content',
            'pub_date', 'pub_date_tz', 'image_url', 'video_url',
            'source_id', 'source_name', 'source_icon', 'language',
            'country', 'category', 'keywords', 'creator', 'created_at'
        ]
        read_only_fields = fields


def process_single_api_call(api_url, params):
    """
    Helper function to process a single API call and return processed data.
    """
    # Make API request
    response = requests.get(api_url, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    if data.get('status') != 'success':
        raise Exception(f"API request failed: {data}")
    
    # Store API response metadata
    api_response = NewsAPIResponse.objects.create(
        status=data.get('status'),
        total_results=data.get('totalResults', 0),
        next_page=data.get('nextPage'),
        query_params=params
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
            else:
                articles_updated += 1
                
        except Exception as e:
            print(f"Error processing article {article_data.get('article_id')}: {str(e)}")
            articles_skipped += 1
            continue
    
    return {
        'api_response_id': api_response.id,
        'total_results': data.get('totalResults', 0),
        'articles_processed': len(data.get('results', [])),
        'articles_created': articles_created,
        'articles_updated': articles_updated,
        'articles_skipped': articles_skipped,
        'query': params.get('q', '')
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def fetch_and_store_news(request):
    """
    Public endpoint: Fetch news from NewsData.io API and store in database. No authentication required.
    Calls multiple APIs sequentially with different query parameters.
    """
    try:
        # API configuration
        # Try environment, then Django settings, then decouple config
        api_url = os.getenv("NEWS_API_URL", None)
        api_key = os.getenv("NEWS_API_KEY", None)
        
        # Fallback to decouple config if still missing (for .env support)
        if not api_url:
            try:
                from decouple import config as decouple_config
                api_url = decouple_config("NEWS_API_URL", default=None)
            except Exception:
                api_url = None
        if not api_key:
            try:
                from decouple import config as decouple_config
                api_key = decouple_config("NEWS_API_KEY", default=None)
            except Exception:
                api_key = None
        
        if not api_key:
            return Response({
                'error': 'NEWS_API_KEY is required',
                'message': 'Set NEWS_API_KEY in your environment or .env file.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if not api_url:
            return Response({
                'error': 'NEWS_API_URL is required',
                'message': 'Set NEWS_API_URL in your environment or .env file.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Define all query parameter sets
        query_params_list = [
            {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate',
                'country': 'in'
            },
            {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate AND finance',
                'country': 'in'
            },
            {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate AND economy',
                'country': 'in'
            },
            {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate AND stockmarket',
                'country': 'in'
            },
            {
                'apikey': api_key,
                'language': 'en',
                'q': 'realestate AND politics',
                'country': 'in'
            }
        ]
        
        # Process each API call sequentially
        all_results = []
        total_articles_created = 0
        total_articles_updated = 0
        total_articles_skipped = 0
        total_results_count = 0
        
        for i, params in enumerate(query_params_list, 1):
            try:
                print(f"Processing API call {i}/{len(query_params_list)} with query: {params['q']}")
                
                # Process single API call
                result = process_single_api_call(api_url, params)
                all_results.append(result)
                
                # Accumulate totals
                total_articles_created += result['articles_created']
                total_articles_updated += result['articles_updated']
                total_articles_skipped += result['articles_skipped']
                total_results_count += result['total_results']
                
                print(f"Completed API call {i}: {result['articles_created']} created, {result['articles_updated']} updated, {result['articles_skipped']} skipped")
                
            except Exception as e:
                print(f"Error in API call {i} with query '{params['q']}': {str(e)}")
                all_results.append({
                    'query': params['q'],
                    'error': str(e),
                    'articles_created': 0,
                    'articles_updated': 0,
                    'articles_skipped': 0,
                    'total_results': 0
                })
                continue
        
        return Response({
            'success': True,
            'message': 'Sequential news data fetching completed',
            'summary': {
                'total_api_calls': len(query_params_list),
                'successful_calls': len([r for r in all_results if 'error' not in r]),
                'failed_calls': len([r for r in all_results if 'error' in r]),
                'total_articles_created': total_articles_created,
                'total_articles_updated': total_articles_updated,
                'total_articles_skipped': total_articles_skipped,
                'total_results_from_api': total_results_count
            },
            'detailed_results': all_results
        }, status=status.HTTP_200_OK)
        
    except requests.RequestException as e:
        return Response({
            'error': 'Failed to fetch news from API',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_latest_news(request):
    """
    Public endpoint: Get the 10 most recent news articles from the database.
    No authentication required.
    """
    try:
        # Get the 10 most recent articles, ordered by publication date (newest first)
        latest_articles = NewsArticle.objects.all().order_by('-pub_date')[:15]
        
        # Serialize the data
        serializer = NewsArticleSerializer(latest_articles, many=True)
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'results': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch latest news',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_news_articles(request):
    """
    Public endpoint: Get stored news articles with optional filtering. No authentication required.
    """
    try:
        # Query parameters for filtering
        source_id = request.GET.get('source_id')
        category = request.GET.get('category')
        language = request.GET.get('language', 'english')
        limit = int(request.GET.get('limit', 20))
        
        # Build query
        queryset = NewsArticle.objects.all()
        
        if source_id:
            queryset = queryset.filter(source_id=source_id)
        if category:
            queryset = queryset.filter(category__contains=[category])
        if language:
            queryset = queryset.filter(language=language)
        
        # Limit results
        articles = queryset[:limit]
        
        # Serialize data
        articles_data = []
        for article in articles:
            articles_data.append({
                'article_id': article.article_id,
                'title': article.title,
                'link': article.link,
                'description': article.description,
                'pub_date': article.pub_date.isoformat(),
                'source_name': article.source_name,
                'category': article.category,
                'keywords': article.keywords,
                'creator': article.creator,
                'image_url': article.image_url,
                'created_at': article.created_at.isoformat()
            })
        
        return Response({
            'success': True,
            'count': len(articles_data),
            'articles': articles_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve articles',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# ALERT MANAGEMENT ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unsent_alerts(request):
    """
    Get all alerts where is_sent = false
    """
    try:
        # Get all unsent alerts ordered by creation date
        alerts = Alert.objects.filter(is_sent=False).order_by('-created_at')
        
        # Serialize data
        serializer = AlertSerializer(alerts, many=True)
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'alerts': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve unsent alerts',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_and_mark_accepted_alerts(request):
    """
    Get alerts where is_sent = false and is_accept = true, 
    then update corresponding budget items and mark alerts as sent
    """
    try:
        from budget.models import ProjectCosts
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get alerts that are accepted but not sent yet
        alerts = Alert.objects.filter(is_sent=False, is_accept=True).order_by('-created_at')
        
        if not alerts.exists():
            return Response({
                'success': True,
                'message': 'No accepted unsent alerts found',
                'count': 0,
                'updated_alerts_count': 0,
                'updated_budget_items': 0,
                'alerts': []
            }, status=status.HTTP_200_OK)
        
        # Serialize the data before updating
        serializer = AlertSerializer(alerts, many=True)
        alerts_data = serializer.data
        
        updated_budget_items = 0
        budget_update_errors = []
        budget_update_details = []
        
        # Update corresponding budget items for each accepted alert
        for alert in alerts:
            try:
                # Validate alert data before processing
                if not alert.category_name or not alert.item:
                    budget_update_errors.append(f'Alert #{alert.alert_id}: Missing category_name or item data')
                    continue
                
                # Try multiple matching strategies for better accuracy
                project_costs = None
                
                # Strategy 1: Exact match on category_name and item_description
                project_costs = ProjectCosts.objects.filter(
                    category_name__iexact=alert.category_name.strip(),
                    item_description__iexact=alert.item.strip()
                ).first()
                
                # Strategy 2: If no exact match, try partial matching
                if not project_costs:
                    project_costs = ProjectCosts.objects.filter(
                        category_name__icontains=alert.category_name.strip(),
                        item_description__icontains=alert.item.strip()
                    ).first()
                
                # Strategy 3: Try matching just on item_description if category doesn't match
                if not project_costs:
                    project_costs = ProjectCosts.objects.filter(
                        item_description__iexact=alert.item.strip()
                    ).first()
                
                if project_costs:
                    # Store original values for logging
                    original_values = {
                        'supplier_brand': project_costs.supplier_brand,
                        'rate_per_unit': project_costs.rate_per_unit,
                        'quantity': project_costs.quantity,
                        'line_total': project_costs.line_total
                    }
                    
                    # Set change tracking fields
                    project_costs._changed_by = f'alert_system_{request.user.username}'
                    project_costs._change_reason = f'Updated from accepted alert #{alert.alert_id}: {alert.decision[:100]}'
                    
                    # Update with new values from the alert (only if they exist and are different)
                    changes_made = []
                    
                    if alert.new_supplier_brand and alert.new_supplier_brand != project_costs.supplier_brand:
                        project_costs.supplier_brand = alert.new_supplier_brand
                        changes_made.append(f'supplier_brand: {original_values["supplier_brand"]} → {alert.new_supplier_brand}')
                    
                    if alert.new_rate_per_unit and alert.new_rate_per_unit != project_costs.rate_per_unit:
                        project_costs.rate_per_unit = alert.new_rate_per_unit
                        changes_made.append(f'rate_per_unit: {original_values["rate_per_unit"]} → {alert.new_rate_per_unit}')
                    
                    if alert.quantity and alert.quantity != project_costs.quantity:
                        project_costs.quantity = alert.quantity
                        changes_made.append(f'quantity: {original_values["quantity"]} → {alert.quantity}')
                    
                    # Only save if there are actual changes
                    if changes_made:
                        # Save will automatically calculate line_total and handle versioning
                        project_costs.save()
                        updated_budget_items += 1
                        
                        budget_update_details.append({
                            'alert_id': alert.alert_id,
                            'project_cost_id': project_costs.id,
                            'changes': changes_made,
                            'new_line_total': project_costs.line_total
                        })
                        
                        logger.info(f'Updated ProjectCost ID {project_costs.id} from Alert #{alert.alert_id}: {", ".join(changes_made)}')
                    else:
                        budget_update_errors.append(f'Alert #{alert.alert_id}: No changes needed - values already match')
                        
                else:
                    error_msg = f'Alert #{alert.alert_id}: No matching budget item found for category "{alert.category_name}" and item "{alert.item}"'
                    budget_update_errors.append(error_msg)
                    logger.warning(error_msg)
                    
            except Exception as e:
                error_msg = f'Alert #{alert.alert_id}: Error updating budget item - {str(e)}'
                budget_update_errors.append(error_msg)
                logger.error(error_msg)
        
        # Update all these alerts to mark them as sent
        updated_alerts_count = alerts.update(is_sent=True)
        
        response_data = {
            'success': True,
            'message': f'Retrieved and marked {updated_alerts_count} accepted alerts as sent, updated {updated_budget_items} budget items',
            'count': len(alerts_data),
            'updated_alerts_count': updated_alerts_count,
            'updated_budget_items': updated_budget_items,
            'alerts': alerts_data,
            'budget_update_details': budget_update_details
        }
        
        if budget_update_errors:
            response_data['budget_update_warnings'] = budget_update_errors
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve and update accepted alerts',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_alert_status(request, alert_id):
    """
    Update the is_accept status of a specific alert
    
    Expected payload:
    {
        "is_accept": true/false
    }
    """
    try:
        alert = Alert.objects.get(alert_id=alert_id)
        
        # Validate the request data
        serializer = AlertStatusUpdateSerializer(alert, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_alert = serializer.save()
            
            # Return updated alert data
            response_serializer = AlertSerializer(updated_alert)
            
            return Response({
                'success': True,
                'message': f'Alert {alert_id} status updated successfully',
                'alert': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        else:
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Alert.DoesNotExist:
        return Response({
            'error': 'Alert not found',
            'message': f'Alert with ID {alert_id} does not exist'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        return Response({
            'error': 'Failed to update alert status',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
