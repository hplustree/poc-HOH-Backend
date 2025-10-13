from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import json


class Projects(models.Model):
    """
    Model representing projects.
    Based on the projects table schema.
    """
    name = models.CharField(max_length=150, help_text="e.g. Corporate Building Project")
    location = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. New York, NY")
    start_date = models.DateField(blank=True, null=True, help_text="Project start date")
    end_date = models.DateField(blank=True, null=True, help_text="Project end date")
    total_project_cost = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Total project cost including all costs and overheads")
    version_number = models.PositiveIntegerField(default=1, help_text="Current version number")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """Override save to handle versioning"""
        # Handle versioning for updates
        if self.pk:  # If this is an update
            try:
                old_instance = Projects.objects.get(pk=self.pk)
                # Check if any significant field has changed
                fields_to_track = ['name', 'location', 'start_date', 'end_date', 'total_project_cost']
                has_changes = any(getattr(old_instance, field) != getattr(self, field) for field in fields_to_track)
                
                if has_changes:
                    # Create version record before updating
                    ProjectVersion.objects.create(
                        original_record=old_instance,
                        name=old_instance.name,
                        location=old_instance.location,
                        start_date=old_instance.start_date,
                        end_date=old_instance.end_date,
                        total_project_cost=old_instance.total_project_cost,
                        version_number=old_instance.version_number,
                        changed_by=getattr(self, '_changed_by', None),
                        change_reason=getattr(self, '_change_reason', 'Updated')
                    )
                    # Increment version number
                    self.version_number = old_instance.version_number + 1
            except Projects.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def calculate_total_cost(self):
        """Calculate and update total project cost from all related costs and overheads"""
        total_costs = sum(cost.line_total for cost in self.projectcosts_set.all())
        total_overheads = sum(overhead.amount for overhead in self.projectoverheads_set.all())
        self.total_project_cost = total_costs + total_overheads
        return self.total_project_cost


class ProjectCosts(models.Model):
    """
    Model representing project costs with categories and items.
    Based on the project_costs table schema.
    """
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, null=True, blank=True, help_text="Reference to the project")
    category_code = models.CharField(max_length=10, help_text="e.g. A, B, C, D")
    category_name = models.CharField(max_length=100, help_text="e.g. Civil & Structural Works")
    item_description = models.CharField(max_length=255, help_text="e.g. Site preparation & excavation")
    supplier_brand = models.CharField(max_length=150, blank=True, null=True, help_text="e.g. BuildSmart Contractors")
    unit = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. Lump sum, m³, m², Nos")
    quantity = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 200000")
    rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 200.00")
    line_total = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 40000000.00")
    category_total = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, help_text="Total of the category")
    version_number = models.PositiveIntegerField(default=1, help_text="Current version number")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_costs'
        verbose_name = 'Project Cost'
        verbose_name_plural = 'Project Costs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} - {self.category_code} - {self.item_description}"

    def save(self, *args, **kwargs):
        """Override save to calculate line_total automatically and handle versioning"""
        # Calculate line_total
        if self.quantity and self.rate_per_unit:
            self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.rate_per_unit))
        
        # Handle versioning for updates
        if self.pk:  # If this is an update
            try:
                old_instance = ProjectCosts.objects.get(pk=self.pk)
                # Check if any significant field has changed
                fields_to_track = ['quantity', 'rate_per_unit', 'supplier_brand', 'category_total']
                has_changes = any(getattr(old_instance, field) != getattr(self, field) for field in fields_to_track)
                
                if has_changes:
                    # Create version record before updating
                    ProjectCostVersion.objects.create(
                        original_record=old_instance,
                        project=old_instance.project,
                        category_code=old_instance.category_code,
                        category_name=old_instance.category_name,
                        item_description=old_instance.item_description,
                        supplier_brand=old_instance.supplier_brand,
                        unit=old_instance.unit,
                        quantity=old_instance.quantity,
                        rate_per_unit=old_instance.rate_per_unit,
                        line_total=old_instance.line_total,
                        category_total=old_instance.category_total,
                        version_number=old_instance.version_number,
                        changed_by=getattr(self, '_changed_by', None),
                        change_reason=getattr(self, '_change_reason', 'Updated')
                    )
                    # Increment version number
                    self.version_number = old_instance.version_number + 1
            except ProjectCosts.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)


class ProjectOverheads(models.Model):
    """
    Model representing project overheads like contingency, contractor margin, etc.
    Based on the project_overheads table schema.
    """
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, null=True, blank=True, help_text="Reference to the project")
    overhead_type = models.CharField(max_length=50, help_text="e.g. Contingency, Contractor Margin")
    description = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. Provided in your BOQ")
    basis = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Percentage of BOQ")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 6.95, 10")
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 5350000, 8235000")
    version_number = models.PositiveIntegerField(default=1, help_text="Current version number")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_overheads'
        verbose_name = 'Project Overhead'
        verbose_name_plural = 'Project Overheads'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} - {self.overhead_type} ({self.percentage}%)"
    
    def save(self, *args, **kwargs):
        """Override save to handle versioning"""
        # Handle versioning for updates
        if self.pk:  # If this is an update
            try:
                old_instance = ProjectOverheads.objects.get(pk=self.pk)
                # Check if any significant field has changed
                fields_to_track = ['percentage', 'amount', 'overhead_type', 'description']
                has_changes = any(getattr(old_instance, field) != getattr(self, field) for field in fields_to_track)
                
                if has_changes:
                    # Create version record before updating
                    ProjectOverheadVersion.objects.create(
                        original_record=old_instance,
                        project=old_instance.project,
                        overhead_type=old_instance.overhead_type,
                        description=old_instance.description,
                        basis=old_instance.basis,
                        percentage=old_instance.percentage,
                        amount=old_instance.amount,
                        version_number=old_instance.version_number,
                        changed_by=getattr(self, '_changed_by', None),
                        change_reason=getattr(self, '_change_reason', 'Updated')
                    )
                    # Increment version number
                    self.version_number = old_instance.version_number + 1
            except ProjectOverheads.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)


class ProjectCostVersion(models.Model):
    """
    Model to store version history of ProjectCosts.
    Tracks all changes made to project cost items.
    """
    original_record = models.ForeignKey(ProjectCosts, on_delete=models.CASCADE, help_text="Reference to the original record")
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, null=True, blank=True, help_text="Reference to the project")
    category_code = models.CharField(max_length=10, help_text="e.g. A, B, C, D")
    category_name = models.CharField(max_length=100, help_text="e.g. Civil & Structural Works")
    item_description = models.CharField(max_length=255, help_text="e.g. Site preparation & excavation")
    supplier_brand = models.CharField(max_length=150, blank=True, null=True, help_text="e.g. BuildSmart Contractors")
    unit = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. Lump sum, m³, m², Nos")
    quantity = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 200000")
    rate_per_unit = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 200.00")
    line_total = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 40000000.00")
    category_total = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, help_text="Total of the category")
    version_number = models.PositiveIntegerField(help_text="Version number at the time of this record")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="User who made the change")
    change_reason = models.CharField(max_length=255, default="Updated", help_text="Reason for the change")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this version was created")

    class Meta:
        db_table = 'project_cost_versions'
        verbose_name = 'Project Cost Version'
        verbose_name_plural = 'Project Cost Versions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.original_record} - Version {self.version_number}"


class ProjectOverheadVersion(models.Model):
    """
    Model to store version history of ProjectOverheads.
    Tracks all changes made to project overhead items.
    """
    original_record = models.ForeignKey(ProjectOverheads, on_delete=models.CASCADE, help_text="Reference to the original record")
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, null=True, blank=True, help_text="Reference to the project")
    overhead_type = models.CharField(max_length=50, help_text="e.g. Contingency, Contractor Margin")
    description = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. Provided in your BOQ")
    basis = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Percentage of BOQ")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 6.95, 10")
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="e.g. 5350000, 8235000")
    version_number = models.PositiveIntegerField(help_text="Version number at the time of this record")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="User who made the change")
    change_reason = models.CharField(max_length=255, default="Updated", help_text="Reason for the change")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this version was created")

    class Meta:
        db_table = 'project_overhead_versions'
        verbose_name = 'Project Overhead Version'
        verbose_name_plural = 'Project Overhead Versions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.original_record} - Version {self.version_number}"


class ProjectVersion(models.Model):
    """
    Model to store version history of Projects.
    Tracks all changes made to project items.
    """
    original_record = models.ForeignKey(Projects, on_delete=models.CASCADE, help_text="Reference to the original record")
    name = models.CharField(max_length=150, help_text="e.g. Corporate Building Project")
    location = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. New York, NY")
    start_date = models.DateField(blank=True, null=True, help_text="Project start date")
    end_date = models.DateField(blank=True, null=True, help_text="Project end date")
    total_project_cost = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total project cost at the time of this version")
    version_number = models.PositiveIntegerField(help_text="Version number at the time of this record")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="User who made the change")
    change_reason = models.CharField(max_length=255, default="Updated", help_text="Reason for the change")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this version was created")

    class Meta:
        db_table = 'project_versions'
        verbose_name = 'Project Version'
        verbose_name_plural = 'Project Versions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.original_record.name} - Version {self.version_number}"
