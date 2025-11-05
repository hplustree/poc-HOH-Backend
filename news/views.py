import os
import requests
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from .models import NewsArticle, NewsAPIResponse, Alert
from .serializers import (AlertSerializer, AlertStatusUpdateSerializer, 
                         NewsArticleSerializer, NewsDecisionAcceptRequestSerializer, 
                         NewsDecisionAcceptResponseSerializer, MLDecisionResponseSerializer)
from budget.models import Projects, ProjectCosts, ProjectOverheads
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)



def process_single_api_call(api_url, params):
    """
    Helper function to process a single API call and return processed data.
    """
    # Make API request
    response = requests.get(api_url, params=params, timeout=3000)
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
            logger.error(f"Error processing article {article_data.get('article_id')}: {str(e)}")
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
                logger.info(f"Processing API call {i}/{len(query_params_list)} with query: {params['q']}")
                
                # Process single API call
                result = process_single_api_call(api_url, params)
                all_results.append(result)
                
                # Accumulate totals
                total_articles_created += result['articles_created']
                total_articles_updated += result['articles_updated']
                total_articles_skipped += result['articles_skipped']
                total_results_count += result['total_results']
                
                logger.info(f"Completed API call {i}: {result['articles_created']} created, {result['articles_updated']} updated, {result['articles_skipped']} skipped")
                
            except Exception as e:
                logger.error(f"Error in API call {i} with query '{params['q']}': {str(e)}")
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
    Get alerts from previous day where is_sent = false and is_accept = false
    """
    try:
        # Calculate previous day date range
        now = timezone.now()
        previous_day_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        previous_day_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get unsent alerts from previous day only where is_accept = False
        alerts = Alert.objects.filter(
            is_sent=False,
            is_accept=False,
            created_at__gte=previous_day_start,
            created_at__lte=previous_day_end
        ).order_by('-created_at')
        
        # Serialize data
        serializer = AlertSerializer(alerts, many=True)
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'alerts': serializer.data,
            'filter_info': {
                'previous_day_start': previous_day_start.isoformat(),
                'previous_day_end': previous_day_end.isoformat(),
                'current_time': now.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve previous day unsent alerts',
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
                        # Save will automatically calculate line_total and create version record
                        logger.info(f'Creating version record for ProjectCost ID {project_costs.id} from Alert #{alert.alert_id}')
                        original_version = project_costs.version_number
                        project_costs.save()
                        logger.info(f'Version record created with version {original_version + 1}. Original cost item remains unchanged.')
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




def get_latest_project_costing_data():
    """
    Get the latest project costing data in the required format.
    Uses the unified costing generator from chatapp.utils.
    """
    try:
        from chatapp.utils import generate_costing_json_from_db
        
        result = generate_costing_json_from_db(project_id=None, include_wrapper=False)
        
        # Handle error cases
        if result.get("status") == "error":
            return None
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting latest project costing data: {str(e)}")
        return None


def build_updated_costing_parameter(alerts):
    """
    Build the updated_costing_parameter from alert raw_response data
    """
    updated_costing_parameter = {}
    
    for index, alert in enumerate(alerts, 1):
        try:
            # Use the raw_response data stored in the alert
            raw_response = alert.raw_response
            
            # Build the structure from alert data
            updated_costing_parameter[str(index)] = {
                "decision": alert.decision,
                "reason": alert.reason,
                "suggestion": alert.suggestion,
                "updated_costing": {
                    "category_name": alert.category_name or "",
                    "item": alert.item or "",
                    "old_values": {
                        "supplier_brand": alert.old_supplier_brand or "",
                        "rate_per_unit": float(alert.old_rate_per_unit) if alert.old_rate_per_unit else 0,
                        "line_total": float(alert.old_line_total) if alert.old_line_total else 0
                    },
                    "new_values": {
                        "supplier_brand": alert.new_supplier_brand or "",
                        "rate_per_unit": float(alert.new_rate_per_unit) if alert.new_rate_per_unit else 0,
                        "line_total": float(alert.new_line_total) if alert.new_line_total else 0
                    },
                    "unit": alert.unit or "",
                    "quantity": float(alert.quantity) if alert.quantity else 0,
                    "cost_impact": float(alert.cost_impact) if alert.cost_impact else 0,
                    "impact_reason": alert.impact_reason or ""
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing alert {alert.alert_id}: {str(e)}")
            continue
    
    return updated_costing_parameter


def update_budget_from_external_response(external_response_data, user, alert_ids):
    """
    Update budget data from external API response with version control
    """
    try:
        from django.db import transaction
        from decimal import Decimal
        
        update_summary = {
            'updated_project': False,
            'updated_costs': 0,
            'updated_overheads': 0,
            'errors': []
        }
        
        with transaction.atomic():
            # Get the latest project
            latest_project = Projects.objects.order_by('-updated_at').first()
            
            if not latest_project:
                update_summary['errors'].append('No project found to update')
                return update_summary
            
            # Update project data if changed
            project_data = external_response_data.get('project', {})
            if project_data:
                project_changed = False
                original_name = latest_project.name
                original_location = latest_project.location
                original_start_date = latest_project.start_date
                original_end_date = latest_project.end_date
                original_total_cost = latest_project.total_cost
                
                if project_data.get('name') and project_data['name'] != latest_project.name:
                    latest_project.name = project_data['name']
                    project_changed = True
                
                if project_data.get('location') and project_data['location'] != latest_project.location:
                    latest_project.location = project_data['location']
                    project_changed = True
                
                if project_data.get('start_date') and project_data['start_date'] != latest_project.start_date:
                    latest_project.start_date = project_data['start_date']
                    project_changed = True
                
                if project_data.get('end_date') and project_data['end_date'] != latest_project.end_date:
                    latest_project.end_date = project_data['end_date']
                    project_changed = True
                
                if (project_data.get('total_cost') is not None and 
                    float(project_data['total_cost']) != float(latest_project.total_cost or 0)):
                    latest_project.total_cost = Decimal(str(project_data['total_cost']))
                    project_changed = True
                
                if project_changed:
                    latest_project._changed_by = f'news_decision_api_{user.username}'
                    latest_project._change_reason = f'Updated from news decision API with alerts: {alert_ids}'
                    logger.info(f'Creating version record for project changes from news decision API')
                    original_version = latest_project.version_number
                    latest_project.save()
                    logger.info(f'Project version record created with version {original_version + 1}. Original project remains unchanged.')
                    update_summary['updated_project'] = True
            
            # Update cost line items
            cost_line_items = external_response_data.get('cost_line_items', [])
            for item_data in cost_line_items:
                try:
                    # Find matching cost item by category and description
                    project_cost = ProjectCosts.objects.filter(
                        project=latest_project,
                        category_code=item_data.get('category_code'),
                        item_description=item_data.get('item_description')
                    ).first()
                    
                    if project_cost:
                        # Check if any values have changed
                        changes_made = []
                        
                        if (item_data.get('supplier_brand') and 
                            item_data['supplier_brand'] != project_cost.supplier_brand):
                            project_cost.supplier_brand = item_data['supplier_brand']
                            changes_made.append('supplier_brand')
                        
                        if (item_data.get('quantity') and 
                            float(item_data['quantity']) != float(project_cost.quantity)):
                            project_cost.quantity = Decimal(str(item_data['quantity']))
                            changes_made.append('quantity')
                        
                        if (item_data.get('rate_per_unit') and 
                            float(item_data['rate_per_unit']) != float(project_cost.rate_per_unit)):
                            project_cost.rate_per_unit = Decimal(str(item_data['rate_per_unit']))
                            changes_made.append('rate_per_unit')
                        
                        if (item_data.get('category_total') and 
                            float(item_data['category_total']) != float(project_cost.category_total or 0)):
                            project_cost.category_total = Decimal(str(item_data['category_total']))
                            changes_made.append('category_total')
                        
                        # Only save if there are changes
                        if changes_made:
                            project_cost._changed_by = f'news_decision_api_{user.username}'
                            project_cost._change_reason = f'Updated from news decision API with alerts: {alert_ids} - Changed: {", ".join(changes_made)}'
                            logger.info(f'Creating version record for ProjectCost ID {project_cost.id} from news decision API')
                            original_version = project_cost.version_number
                            project_cost.save()
                            logger.info(f'Cost version record created with version {original_version + 1}. Original cost item remains unchanged.')
                            update_summary['updated_costs'] += 1
                            
                            logger.info(f'Version record created for ProjectCost ID {project_cost.id}: {", ".join(changes_made)}')
                    
                except Exception as e:
                    error_msg = f'Error updating cost item {item_data.get("item_description", "unknown")}: {str(e)}'
                    update_summary['errors'].append(error_msg)
                    logger.error(error_msg)
            
            # Update overheads
            overheads_data = external_response_data.get('overheads', [])
            for overhead_data in overheads_data:
                try:
                    # Find matching overhead by type
                    project_overhead = ProjectOverheads.objects.filter(
                        project=latest_project,
                        overhead_type=overhead_data.get('overhead_type')
                    ).first()
                    
                    if project_overhead:
                        # Check if any values have changed
                        changes_made = []
                        
                        if (overhead_data.get('percentage') and 
                            float(overhead_data['percentage']) != float(project_overhead.percentage)):
                            project_overhead.percentage = Decimal(str(overhead_data['percentage']))
                            changes_made.append('percentage')
                        
                        if (overhead_data.get('amount') and 
                            float(overhead_data['amount']) != float(project_overhead.amount)):
                            project_overhead.amount = Decimal(str(overhead_data['amount']))
                            changes_made.append('amount')
                        
                        if (overhead_data.get('description') and 
                            overhead_data['description'] != project_overhead.description):
                            project_overhead.description = overhead_data['description']
                            changes_made.append('description')
                        
                        # Only save if there are changes
                        if changes_made:
                            project_overhead._changed_by = f'news_decision_api_{user.username}'
                            project_overhead._change_reason = f'Updated from news decision API with alerts: {alert_ids} - Changed: {", ".join(changes_made)}'
                            logger.info(f'Creating version record for ProjectOverhead ID {project_overhead.id} from news decision API')
                            original_version = project_overhead.version_number
                            project_overhead.save()
                            logger.info(f'Overhead version record created with version {original_version + 1}. Original overhead remains unchanged.')
                            update_summary['updated_overheads'] += 1
                            
                            logger.info(f'Version record created for ProjectOverhead ID {project_overhead.id}: {", ".join(changes_made)}')
                    
                    else:
                        # Create new overhead if it doesn't exist
                        if overhead_data.get('overhead_type') and overhead_data.get('percentage') and overhead_data.get('amount'):
                            new_overhead = ProjectOverheads.objects.create(
                                project=latest_project,
                                overhead_type=overhead_data['overhead_type'],
                                description=overhead_data.get('description', ''),
                                basis=overhead_data.get('basis', 'On total cost'),
                                percentage=Decimal(str(overhead_data['percentage'])),
                                amount=Decimal(str(overhead_data['amount']))
                            )
                            new_overhead._changed_by = f'news_decision_api_{user.username}'
                            new_overhead._change_reason = f'Created from news decision API with alerts: {alert_ids}'
                            new_overhead.save()  # This is a new record, so no version control needed
                            update_summary['updated_overheads'] += 1
                            
                            logger.info(f'Created new ProjectOverhead ID {new_overhead.id}: {overhead_data["overhead_type"]}')
                
                except Exception as e:
                    error_msg = f'Error updating overhead {overhead_data.get("overhead_type", "unknown")}: {str(e)}'
                    update_summary['errors'].append(error_msg)
                    logger.error(error_msg)
        
        return update_summary
        
    except Exception as e:
        logger.error(f"Error updating budget from external response: {str(e)}")
        return {
            'updated_project': False,
            'updated_costs': 0,
            'updated_overheads': 0,
            'errors': [f'Database update failed: {str(e)}']
        }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_news_alerts_and_call_decision_api(request):
    """
    Process news alerts by IDs and call the external news-decision-accept API
    
    Expected payload:
    {
        "alert_ids": [1, 2, 3, 4]
    }
    """
    try:
        # Validate request data
        serializer = NewsDecisionAcceptRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid request data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        alert_ids = serializer.validated_data['alert_ids']
        
        # Fetch alerts by IDs
        alerts = Alert.objects.filter(alert_id__in=alert_ids).order_by('alert_id')
        
        if not alerts.exists():
            return Response({
                'error': 'No alerts found',
                'message': f'No alerts found for IDs: {alert_ids}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get latest costing data from budget models
        costing_json = get_latest_project_costing_data()
        
        if not costing_json:
            return Response({
                'error': 'No project costing data found',
                'message': 'Unable to fetch latest project costing data from budget models'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Build updated_costing_parameter from alerts
        updated_costing_parameter = build_updated_costing_parameter(alerts)
        
        # Prepare payload for external API
        external_api_payload = {
            "costing_json": costing_json,
            "updated_costing_parameter": updated_costing_parameter
        }
        
        # Call external news-decision-accept API
        external_api_url =  os.getenv("ML_BASE_URI") + "api/news-decision-accept"
        
        try:
            response = requests.post(
                external_api_url,
                json=external_api_payload,
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                timeout=3000
            )
            response.raise_for_status()
            external_response_data = response.json()
            
            # Update database with the response data and version control
            update_result = update_budget_from_external_response(external_response_data, request.user, alert_ids)
            
            # Mark processed alerts as accepted
            updated_alerts_count = alerts.update(is_accept=True, accepted_at=timezone.now())
            logger.info(f"Marked {updated_alerts_count} alerts as accepted: {alert_ids}")
            
        except requests.RequestException as e:
            logger.error(f"Error calling external API: {str(e)}")
            return Response({
                'error': 'Failed to call external news-decision-accept API',
                'details': str(e),
                'payload_sent': external_api_payload
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Prepare response data
        processed_alerts = []
        for alert in alerts:
            processed_alerts.append({
                'alert_id': alert.alert_id,
                'decision': alert.decision,
                'category_name': alert.category_name,
                'item': alert.item,
                'cost_impact': float(alert.cost_impact) if alert.cost_impact else 0
            })
        
        return Response({
            'success': True,
            'message': f'Successfully processed {len(alerts)} alerts, called external API, updated database, and marked alerts as accepted',
            'processed_alerts_count': len(alerts),
            'alerts_marked_accepted': updated_alerts_count,
            'processed_alerts': processed_alerts,
            'external_api_response': external_response_data,
            'database_update_summary': update_result,
            'payload_sent': external_api_payload
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in process_news_alerts_and_call_decision_api: {str(e)}")
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_ml_decision_response(request):
    """
    Directly post ML decision API response to save alerts to database
    
    Expected payload:
    {
        "response": {
            "1": {
                "decision": "...",
                "reason": "...",
                "suggestion": "...",
                "updated_costing": {
                    "category_name": "...",
                    "item": "...",
                    "old_values": {...},
                    "new_values": {...},
                    "cost_impact": "...",
                    "impact_reason": "..."
                }
            }
        }
    }
    """
    try:
        # Validate request data
        serializer = MLDecisionResponseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid request data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        response_data = serializer.validated_data['response']
        
        # Use the same save_alerts_to_database function from daily_news_processor
        alerts_saved = 0
        alerts_errors = []
        
        for decision_key, alert_data in response_data.items():
            try:
                # Extract updated costing data if available
                updated_costing = alert_data.get('updated_costing', {})
                old_values = updated_costing.get('old_values', {})
                new_values = updated_costing.get('new_values', {})
                
                # Create Alert object
                alert = Alert.objects.create(
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
                logger.info(f'Saved alert {alert.alert_id} from direct ML response: {alert.decision[:50]}...')
                
            except Exception as e:
                error_msg = f'Error saving alert for key {decision_key}: {str(e)}'
                alerts_errors.append(error_msg)
                logger.error(error_msg)
        
        # Prepare response
        response_message = f'Successfully saved {alerts_saved} alerts to database'
        if alerts_errors:
            response_message += f' with {len(alerts_errors)} errors'
        
        response_data = {
            'success': True,
            'message': response_message,
            'alerts_saved': alerts_saved,
            'total_decision_keys': len(response_data),
            'timestamp': timezone.now().isoformat()
        }
        
        if alerts_errors:
            response_data['errors'] = alerts_errors
        
        logger.info(f'Direct ML response processing completed: {alerts_saved} alerts saved')
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error in post_ml_decision_response: {str(e)}")
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
