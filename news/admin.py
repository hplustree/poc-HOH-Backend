from django.contrib import admin
from .models import NewsArticle, NewsAPIResponse


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ['article_id', 'title', 'source_name', 'pub_date', 'language', 'created_at']
    list_filter = ['language', 'source_name', 'category', 'pub_date', 'created_at']
    search_fields = ['title', 'description', 'source_name', 'keywords']
    readonly_fields = ['article_id', 'created_at', 'updated_at']
    date_hierarchy = 'pub_date'
    
    fieldsets = (
        ('Article Information', {
            'fields': ('article_id', 'title', 'link', 'description', 'content')
        }),
        ('Publication Details', {
            'fields': ('pub_date', 'pub_date_tz', 'creator')
        }),
        ('Media', {
            'fields': ('image_url', 'video_url')
        }),
        ('Source Information', {
            'fields': ('source_id', 'source_name', 'source_priority', 'source_url', 'source_icon')
        }),
        ('Classification', {
            'fields': ('language', 'country', 'category', 'keywords')
        }),
        ('Metadata', {
            'fields': ('duplicate', 'created_at', 'updated_at')
        }),
    )


@admin.register(NewsAPIResponse)
class NewsAPIResponseAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'total_results', 'fetched_at']
    list_filter = ['status', 'fetched_at']
    readonly_fields = ['fetched_at']
    
    fieldsets = (
        ('Response Details', {
            'fields': ('status', 'total_results', 'next_page', 'fetched_at')
        }),
        ('Query Information', {
            'fields': ('query_params',)
        }),
    )
