from django.contrib import admin
from .models import Projects, ProjectCosts, ProjectOverheads


@admin.register(Projects)
class ProjectsAdmin(admin.ModelAdmin):
    """Admin interface for Projects model"""
    
    list_display = [
        'name',
        'location',
        'start_date',
        'end_date',
        'created_at'
    ]
    
    list_filter = [
        'start_date',
        'end_date',
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'name',
        'location'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Project Information', {
            'fields': ('name', 'location')
        }),
        ('Timeline', {
            'fields': ('start_date', 'end_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']


@admin.register(ProjectCosts)
class ProjectCostsAdmin(admin.ModelAdmin):
    """Admin interface for ProjectCosts model"""
    
    list_display = [
        'project', 
        'category_code', 
        'category_name', 
        'item_description', 
        'quantity', 
        'rate_per_unit', 
        'line_total',
        'created_at'
    ]
    
    list_filter = [
        'category_code',
        'project',
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'project__name',
        'category_name',
        'item_description',
        'supplier_brand'
    ]
    
    readonly_fields = ['line_total', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Project Information', {
            'fields': ('project',)
        }),
        ('Category Information', {
            'fields': ('category_code', 'category_name')
        }),
        ('Item Details', {
            'fields': ('item_description', 'supplier_brand', 'unit')
        }),
        ('Cost Calculation', {
            'fields': ('quantity', 'rate_per_unit', 'line_total', 'category_total')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']


@admin.register(ProjectOverheads)
class ProjectOverheadsAdmin(admin.ModelAdmin):
    """Admin interface for ProjectOverheads model"""
    
    list_display = [
        'project',
        'overhead_type',
        'percentage',
        'amount',
        'basis',
        'created_at'
    ]
    
    list_filter = [
        'overhead_type',
        'project',
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'project_name',
        'overhead_type',
        'description',
        'basis'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Project Information', {
            'fields': ('project',)
        }),
        ('Overhead Details', {
            'fields': ('overhead_type', 'description', 'basis')
        }),
        ('Financial Information', {
            'fields': ('percentage', 'amount')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']
