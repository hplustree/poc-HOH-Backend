from django.db import models
from django.contrib.postgres.fields import ArrayField


class NewsArticle(models.Model):
    # Core article fields
    article_id = models.CharField(max_length=255, unique=True, primary_key=True)
    title = models.TextField()
    link = models.URLField(max_length=500)
    description = models.TextField(null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    
    # Publication details
    pub_date = models.DateTimeField()
    pub_date_tz = models.CharField(max_length=10, default='UTC')
    
    # Media URLs
    image_url = models.URLField(max_length=500, null=True, blank=True)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Source information
    source_id = models.CharField(max_length=100)
    source_name = models.CharField(max_length=200)
    source_priority = models.IntegerField(null=True, blank=True)
    source_url = models.URLField(max_length=500, null=True, blank=True)
    source_icon = models.URLField(max_length=500, null=True, blank=True)
    
    # Classification
    language = models.CharField(max_length=50)
    country = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    category = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    keywords = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    creator = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    
    # Metadata
    duplicate = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-pub_date']
        indexes = [
            models.Index(fields=['pub_date']),
            models.Index(fields=['source_id']),
            models.Index(fields=['language']),
        ]
    
    def __str__(self):
        return self.title[:100]


class NewsAPIResponse(models.Model):
    """Store metadata about API calls"""
    status = models.CharField(max_length=20)
    total_results = models.IntegerField()
    next_page = models.CharField(max_length=100, null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    query_params = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-fetched_at']
    
    def __str__(self):
        return f"API Response - {self.status} - {self.total_results} results"
