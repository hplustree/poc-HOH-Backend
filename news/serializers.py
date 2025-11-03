from rest_framework import serializers
from .models import Alert, NewsArticle


class AlertSerializer(serializers.ModelSerializer):
    """Serializer for Alert model"""
    
    class Meta:
        model = Alert
        fields = [
            'alert_id', 'decision_key', 'decision', 'reason', 'suggestion',
            'category_name', 'item', 'unit', 'quantity',
            'old_supplier_brand', 'old_rate_per_unit', 'old_line_total',
            'new_supplier_brand', 'new_rate_per_unit', 'new_line_total',
            'cost_impact', 'impact_reason', 'is_accept', 'is_sent',
            'created_at', 'updated_at', 'accepted_at'
        ]
        read_only_fields = ['alert_id', 'created_at', 'updated_at', 'accepted_at']


class AlertStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating alert acceptance status"""
    
    class Meta:
        model = Alert
        fields = ['is_accept']
    
    def update(self, instance, validated_data):
        """Override update to handle accepted_at timestamp"""
        from django.utils import timezone
        
        is_accept = validated_data.get('is_accept')
        instance.is_accept = is_accept
        
        # Set accepted_at timestamp when accepting
        if is_accept:
            instance.accepted_at = timezone.now()
        else:
            instance.accepted_at = None
            
        instance.save()
        return instance


class NewsArticleSerializer(serializers.ModelSerializer):
    """Serializer for NewsArticle model"""
    
    class Meta:
        model = NewsArticle
        fields = [
            'article_id', 'title', 'link', 'description', 'content',
            'pub_date', 'pub_date_tz', 'image_url', 'video_url',
            'source_id', 'source_name', 'source_icon', 'language',
            'country', 'category', 'keywords', 'creator', 'created_at'
        ]
        read_only_fields = fields


class NewsDecisionAcceptRequestSerializer(serializers.Serializer):
    """Serializer for the news decision accept API request"""
    alert_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of alert IDs to process"
    )


class NewsDecisionAcceptResponseSerializer(serializers.Serializer):
    """Serializer for the news decision accept API response"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    external_api_response = serializers.JSONField()
    processed_alerts = serializers.ListField()
