from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class VersionNumber(models.Model):
    """Base version tracking model"""
    changed_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Projects(models.Model):
    """Main projects table with version control"""
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    version_number = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Fields for tracking changes (not stored in DB, used for versioning logic)
    _changed_by = None
    _change_reason = None

    class Meta:
        db_table = 'projects'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

    def __str__(self):
        return f"{self.name} (v{self.version_number})"

    def save(self, *args, **kwargs):
        """Override save to implement automatic versioning"""
        is_new = self.pk is None
        
        if not is_new:
            # Get the original object to compare changes
            original = Projects.objects.get(pk=self.pk)
            
            # Check if tracked fields have changed
            tracked_fields = ['name', 'location', 'start_date', 'end_date', 'total_cost']
            has_changes = any(
                getattr(self, field) != getattr(original, field) 
                for field in tracked_fields
            )
            
            if has_changes:
                # Create version record before updating
                ProjectVersion.objects.create(
                    project=original,
                    name=original.name,
                    location=original.location,
                    start_date=original.start_date,
                    end_date=original.end_date,
                    total_cost=original.total_cost,
                    version_number=original.version_number,
                    changed_by=getattr(self, '_changed_by', 'system'),
                    change_reason=getattr(self, '_change_reason', 'Updated'),
                    created_at=original.created_at,
                    updated_at=original.updated_at
                )
                
                # Increment version number
                self.version_number = original.version_number + 1
        
        super().save(*args, **kwargs)


class ProjectVersion(VersionNumber):
    """Version history for Projects"""
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='versions')
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    version_number = models.IntegerField()
    change_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'project_versions'
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.project.name} v{self.version_number}"


class ProjectCosts(models.Model):
    """Project costs/line items with version control"""
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='costs')
    category_code = models.CharField(max_length=10)
    category_name = models.CharField(max_length=100)
    item_description = models.CharField(max_length=255)
    supplier_brand = models.CharField(max_length=150, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    category_total = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    version_number = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Fields for tracking changes
    _changed_by = None
    _change_reason = None

    class Meta:
        db_table = 'project_costs'
        verbose_name = 'Project Cost'
        verbose_name_plural = 'Project Costs'

    def __str__(self):
        return f"{self.item_description} - {self.project.name} (v{self.version_number})"

    def save(self, *args, **kwargs):
        """Override save to implement automatic versioning"""
        # Calculate line_total automatically
        self.line_total = self.quantity * self.rate_per_unit
        
        is_new = self.pk is None
        
        if not is_new:
            # Get the original object to compare changes
            original = ProjectCosts.objects.get(pk=self.pk)
            
            # Check if tracked fields have changed
            tracked_fields = ['quantity', 'rate_per_unit', 'supplier_brand', 'category_total']
            has_changes = any(
                getattr(self, field) != getattr(original, field) 
                for field in tracked_fields
            )
            
            if has_changes:
                # Create version record before updating
                ProjectCostVersion.objects.create(
                    project_cost=original,
                    project=original.project,
                    category_code=original.category_code,
                    category_name=original.category_name,
                    item_description=original.item_description,
                    supplier_brand=original.supplier_brand,
                    unit=original.unit,
                    quantity=original.quantity,
                    rate_per_unit=original.rate_per_unit,
                    line_total=original.line_total,
                    category_total=original.category_total,
                    version_number=original.version_number,
                    changed_by=getattr(self, '_changed_by', 'system'),
                    change_reason=getattr(self, '_change_reason', 'Updated'),
                    created_at=original.created_at,
                    updated_at=original.updated_at
                )
                
                # Increment version number
                self.version_number = original.version_number + 1
        
        super().save(*args, **kwargs)


class ProjectCostVersion(VersionNumber):
    """Version history for ProjectCosts"""
    project_cost = models.ForeignKey(ProjectCosts, on_delete=models.CASCADE, related_name='versions')
    project = models.ForeignKey(Projects, on_delete=models.CASCADE)
    category_code = models.CharField(max_length=10)
    category_name = models.CharField(max_length=100)
    item_description = models.CharField(max_length=255)
    supplier_brand = models.CharField(max_length=150, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    category_total = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    version_number = models.IntegerField()
    change_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'project_cost_versions'
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.item_description} v{self.version_number}"


class ProjectOverheads(models.Model):
    """Project overheads with version control"""
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='overheads')
    overhead_type = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True, null=True)
    basis = models.CharField(max_length=100, blank=True, null=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    version_number = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Fields for tracking changes
    _changed_by = None
    _change_reason = None

    class Meta:
        db_table = 'project_overheads'
        verbose_name = 'Project Overhead'
        verbose_name_plural = 'Project Overheads'

    def __str__(self):
        return f"{self.overhead_type} - {self.project.name} (v{self.version_number})"

    def save(self, *args, **kwargs):
        """Override save to implement automatic versioning"""
        is_new = self.pk is None
        
        if not is_new:
            # Get the original object to compare changes
            original = ProjectOverheads.objects.get(pk=self.pk)
            
            # Check if tracked fields have changed
            tracked_fields = ['percentage', 'amount', 'overhead_type', 'description']
            has_changes = any(
                getattr(self, field) != getattr(original, field) 
                for field in tracked_fields
            )
            
            if has_changes:
                # Create version record before updating
                ProjectOverheadVersion.objects.create(
                    project_overhead=original,
                    project=original.project,
                    overhead_type=original.overhead_type,
                    description=original.description,
                    basis=original.basis,
                    percentage=original.percentage,
                    amount=original.amount,
                    version_number=original.version_number,
                    changed_by=getattr(self, '_changed_by', 'system'),
                    change_reason=getattr(self, '_change_reason', 'Updated'),
                    created_at=original.created_at,
                    updated_at=original.updated_at
                )
                
                # Increment version number
                self.version_number = original.version_number + 1
        
        super().save(*args, **kwargs)


class ProjectOverheadVersion(VersionNumber):
    """Version history for ProjectOverheads"""
    project_overhead = models.ForeignKey(ProjectOverheads, on_delete=models.CASCADE, related_name='versions')
    project = models.ForeignKey(Projects, on_delete=models.CASCADE)
    overhead_type = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True, null=True)
    basis = models.CharField(max_length=100, blank=True, null=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    version_number = models.IntegerField()
    change_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'project_overhead_versions'
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.overhead_type} v{self.version_number}"