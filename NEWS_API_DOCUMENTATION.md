# News API Documentation

## Overview
The News app integrates with NewsData.io API to fetch and store news articles related to real estate, finance, and demographic topics from India.

## API Endpoints

### 1. Fetch News
**Endpoint:** `POST /api/news/fetch/`
**Authentication:** Required (JWT Token)
**Description:** Fetches latest news from NewsData.io API and stores in database

**Request:**
```bash
curl -X POST http://localhost:8000/api/news/fetch/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
    "success": true,
    "message": "News data fetched and stored successfully",
    "stats": {
        "total_results": 1556,
        "articles_processed": 10,
        "articles_created": 8,
        "articles_updated": 2,
        "articles_skipped": 0
    },
    "api_response_id": 1
}
```

### 2. Get News Articles
**Endpoint:** `GET /api/news/articles/`
**Authentication:** Required (JWT Token)
**Description:** Retrieves stored news articles with optional filtering

**Query Parameters:**
- `source_id` (optional): Filter by news source
- `category` (optional): Filter by category
- `language` (optional): Filter by language (default: english)
- `limit` (optional): Number of articles to return (default: 20)

**Request:**
```bash
curl -X GET "http://localhost:8000/api/news/articles/?limit=5&category=business" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
    "success": true,
    "count": 5,
    "articles": [
        {
            "article_id": "98db7c99b3a9a3078531e59e620e0d9c",
            "title": "HC Refuses To Stay On Bc Quota Hike, Asks Four Key Questions For State",
            "link": "https://www.deccanchronicle.com/...",
            "description": "State govt claims BC Bills got deemed approved...",
            "pub_date": "2025-10-08T19:07:09+00:00",
            "source_name": "Deccan Chronicle",
            "category": ["politics", "top"],
            "keywords": ["southern states", "telangana", "news"],
            "creator": ["Vujjini Vamshidhar"],
            "image_url": "https://www.deccanchronicle.com/...",
            "created_at": "2025-10-09T09:05:18.123456+00:00"
        }
    ]
}
```

## Management Commands

### Fetch News Command
You can also fetch news using Django management command:

```bash
python manage.py fetch_news
```

This command will:
1. Call the NewsData.io API
2. Store API response metadata
3. Process and store individual articles
4. Handle duplicate articles (update existing ones)
5. Skip articles with paid plan content

## Database Models

### NewsArticle
Stores individual news articles with fields:
- `article_id` (Primary Key)
- `title`, `link`, `description`, `content`
- `pub_date`, `pub_date_tz`
- `image_url`, `video_url`
- Source information (`source_id`, `source_name`, etc.)
- Classification (`language`, `country`, `category`, `keywords`)
- Metadata (`duplicate`, `created_at`, `updated_at`)

### NewsAPIResponse
Stores metadata about API calls:
- `status`, `total_results`, `next_page`
- `fetched_at`, `query_params`

## API Configuration

The NewsData.io API is configured with:
- **API Key:** `pub_9ae5d2fe55a643f88142368151829b43`
- **Language:** English
- **Query:** `realestate OR finance OR demographic`
- **Country:** India

## Admin Interface

Both models are registered in Django Admin with comprehensive interfaces for:
- Viewing and filtering articles
- Searching by title, description, source
- Managing API response history

## Error Handling

The API handles various error scenarios:
- API request failures
- Invalid API responses
- Database errors
- Individual article processing errors

All errors are logged and returned in structured JSON responses.
