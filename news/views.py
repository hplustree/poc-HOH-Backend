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
from .models import NewsArticle, NewsAPIResponse


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


@api_view(['POST'])
@permission_classes([AllowAny])
def fetch_and_store_news(request):
    """
    Public endpoint: Fetch news from NewsData.io API and store in database. No authentication required.
    """
    try:
        # API configuration
        # Try environment, then Django settings, then decouple config
        api_url = os.environ.get("NEWS_API_URL") or getattr(settings, "NEWS_API_URL", None)
        api_key = os.environ.get("NEWS_API_KEY") or getattr(settings, "NEWS_API_KEY", None)
        
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
        
        # Query parameters
        params = {
            'apikey': api_key,
            'language': 'en',
            'q': 'realestate or finance AND economy',
            'country': 'in'
        }
        
        # Make API request
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') != 'success':
            return Response({
                'error': 'API request failed',
                'details': data
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        return Response({
            'success': True,
            'message': 'News data fetched and stored successfully',
            'stats': {
                'total_results': data.get('totalResults', 0),
                'articles_processed': len(data.get('results', [])),
                'articles_created': articles_created,
                'articles_updated': articles_updated,
                'articles_skipped': articles_skipped
            },
            'api_response_id': api_response.id
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
