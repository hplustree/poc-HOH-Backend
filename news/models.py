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


class Alert(models.Model):
    """Store decision API responses and alerts"""
    # Alert identification
    alert_id = models.AutoField(primary_key=True)
    project_id = models.ForeignKey('budget.Projects', on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    decision_key = models.CharField(max_length=50)  # e.g., "1", "2", etc. from response
    
    # Decision details
    decision = models.TextField()
    reason = models.TextField()
    suggestion = models.TextField()
    
    # Updated costing information
    category_name = models.CharField(max_length=200, null=True, blank=True)
    item = models.CharField(max_length=500, null=True, blank=True)
    unit = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Old values
    old_supplier_brand = models.CharField(max_length=200, null=True, blank=True)
    old_rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    old_line_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # New values
    new_supplier_brand = models.CharField(max_length=200, null=True, blank=True)
    new_rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    new_line_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Impact details
    cost_impact = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    impact_reason = models.TextField(null=True, blank=True)
    
    # Alert status
    is_accept = models.BooleanField(default=False, null=True, blank=True)
    is_sent = models.BooleanField(default=False)
    
    # Raw response data (for backup/debugging)
    raw_response = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['is_accept']),
            models.Index(fields=['is_sent']),
            models.Index(fields=['decision_key']),
            models.Index(fields=['project_id']),
        ]
    
    def __str__(self):
        return f"Alert {self.alert_id}: {self.decision[:50]}..."
    
    def accept_alert(self):
        """Mark alert as accepted"""
        from django.utils import timezone
        self.is_accept = True
        self.accepted_at = timezone.now()
        self.save()
