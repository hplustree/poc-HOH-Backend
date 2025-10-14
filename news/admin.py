from django.contrib import admin
from .models import NewsArticle, NewsAPIResponse, Alert


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


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['alert_id', 'decision_key', 'decision_short', 'is_accept', 'is_sent', 'cost_impact', 'created_at']
    list_filter = ['is_accept', 'is_sent', 'created_at', 'category_name', 'old_supplier_brand', 'new_supplier_brand']
    search_fields = ['decision', 'reason', 'suggestion', 'category_name', 'item']
    readonly_fields = ['alert_id', 'created_at', 'updated_at', 'accepted_at']
    date_hierarchy = 'created_at'
    
    actions = ['mark_as_accepted', 'mark_as_not_accepted']
    
    def decision_short(self, obj):
        """Show shortened decision text"""
        return obj.decision[:50] + '...' if len(obj.decision) > 50 else obj.decision
    decision_short.short_description = 'Decision'
    
    def mark_as_accepted(self, request, queryset):
        """Mark selected alerts as accepted"""
        updated = queryset.update(is_accept=True)
        self.message_user(request, f'{updated} alerts marked as accepted.')
    mark_as_accepted.short_description = 'Mark selected alerts as accepted'
    
    def mark_as_not_accepted(self, request, queryset):
        """Mark selected alerts as not accepted"""
        updated = queryset.update(is_accept=False)
        self.message_user(request, f'{updated} alerts marked as not accepted.')
    mark_as_not_accepted.short_description = 'Mark selected alerts as not accepted'
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('alert_id', 'decision_key', 'decision', 'reason', 'suggestion')
        }),
        ('Costing Details', {
            'fields': ('category_name', 'item', 'unit', 'quantity')
        }),
        ('Old Values', {
            'fields': ('old_supplier_brand', 'old_rate_per_unit', 'old_line_total')
        }),
        ('New Values', {
            'fields': ('new_supplier_brand', 'new_rate_per_unit', 'new_line_total')
        }),
        ('Impact', {
            'fields': ('cost_impact', 'impact_reason')
        }),
        ('Status', {
            'fields': ('is_accept', 'is_sent', 'accepted_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
        ('Raw Data', {
            'fields': ('raw_response',),
            'classes': ('collapse',)
        }),
    )
