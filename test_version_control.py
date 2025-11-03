#!/usr/bin/env python3
"""
Test script to verify the new version control logic
"""
import os
import sys
import django

# Setup Django environment
sys.path.append('/home/fx/Desktop/proj/HOH/HOHBackend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hoh_project.settings')
django.setup()

from budget.models import Projects, ProjectCosts, ProjectOverheads, ProjectVersion, ProjectCostVersion, ProjectOverheadVersion
from decimal import Decimal
from django.utils import timezone

def test_project_versioning():
    """Test Projects model version control"""
    print("=== Testing Projects Version Control ===")
    
    # Create a new project
    project = Projects.objects.create(
        name="Test Project",
        location="Test Location",
        total_cost=Decimal('100000.00')
    )
    print(f"Created project: {project} (ID: {project.id})")
    
    # Check initial state
    print(f"Initial version: {project.version_number}")
    print(f"Initial versions count: {ProjectVersion.objects.filter(project=project).count()}")
    
    # Update the project (should create version)
    project.name = "Updated Test Project"
    project._changed_by = "test_user"
    project._change_reason = "Testing version control"
    project.save()
    
    # Check after update
    updated_project = Projects.objects.get(id=project.id)
    print(f"Updated project: {updated_project}")
    print(f"New version: {updated_project.version_number}")
    print(f"Versions count: {ProjectVersion.objects.filter(project=project).count()}")
    
    # Check version record
    version = ProjectVersion.objects.filter(project=project).first()
    if version:
        print(f"Version record: {version.name} (v{version.version_number})")
        print(f"Version changed_by: {version.changed_by}")
    
    print()

def test_project_cost_versioning():
    """Test ProjectCosts model version control"""
    print("=== Testing ProjectCosts Version Control ===")
    
    # Get or create a project
    project = Projects.objects.first()
    if not project:
        project = Projects.objects.create(
            name="Cost Test Project",
            location="Test Location"
        )
    
    # Create a new cost item
    cost = ProjectCosts.objects.create(
        project=project,
        category_code="A01",
        category_name="Foundation",
        item_description="Concrete Foundation",
        quantity=Decimal('100.00'),
        rate_per_unit=Decimal('50.00'),
        line_total=Decimal('5000.00')
    )
    print(f"Created cost: {cost} (ID: {cost.id})")
    print(f"Initial version: {cost.version_number}")
    print(f"Initial line_total: {cost.line_total}")
    
    # Update the cost (should create version)
    cost.quantity = Decimal('150.00')
    cost._changed_by = "test_user"
    cost._change_reason = "Testing cost version control"
    cost.save()
    
    # Check after update
    updated_cost = ProjectCosts.objects.get(id=cost.id)
    print(f"Updated cost: {updated_cost}")
    print(f"New version: {updated_cost.version_number}")
    print(f"New line_total: {updated_cost.line_total}")
    print(f"Versions count: {ProjectCostVersion.objects.filter(project_cost=cost).count()}")
    
    # Check version record
    version = ProjectCostVersion.objects.filter(project_cost=cost).first()
    if version:
        print(f"Version record: {version.item_description} (v{version.version_number})")
        print(f"Version quantity: {version.quantity}, line_total: {version.line_total}")
    
    print()

def test_project_overhead_versioning():
    """Test ProjectOverheads model version control"""
    print("=== Testing ProjectOverheads Version Control ===")
    
    # Get or create a project
    project = Projects.objects.first()
    if not project:
        project = Projects.objects.create(
            name="Overhead Test Project",
            location="Test Location"
        )
    
    # Create a new overhead item
    overhead = ProjectOverheads.objects.create(
        project=project,
        overhead_type="Contingency",
        description="Project Contingency",
        percentage=Decimal('10.00'),
        amount=Decimal('10000.00')
    )
    print(f"Created overhead: {overhead} (ID: {overhead.id})")
    print(f"Initial version: {overhead.version_number}")
    print(f"Initial percentage: {overhead.percentage}")
    
    # Update the overhead (should create version)
    overhead.percentage = Decimal('15.00')
    overhead.amount = Decimal('15000.00')
    overhead._changed_by = "test_user"
    overhead._change_reason = "Testing overhead version control"
    overhead.save()
    
    # Check after update
    updated_overhead = ProjectOverheads.objects.get(id=overhead.id)
    print(f"Updated overhead: {updated_overhead}")
    print(f"New version: {updated_overhead.version_number}")
    print(f"New percentage: {updated_overhead.percentage}")
    print(f"Versions count: {ProjectOverheadVersion.objects.filter(project_overhead=overhead).count()}")
    
    # Check version record
    version = ProjectOverheadVersion.objects.filter(project_overhead=overhead).first()
    if version:
        print(f"Version record: {version.overhead_type} (v{version.version_number})")
        print(f"Version percentage: {version.percentage}, amount: {version.amount}")
    
    print()

def cleanup_test_data():
    """Clean up test data"""
    print("=== Cleaning up test data ===")
    
    # Delete test projects and related data
    test_projects = Projects.objects.filter(name__icontains="Test")
    for project in test_projects:
        print(f"Deleting project: {project}")
        project.delete()
    
    print("Cleanup completed")

if __name__ == "__main__":
    print("Starting Version Control Tests...")
    print()
    
    try:
        test_project_versioning()
        test_project_cost_versioning()
        test_project_overhead_versioning()
        
        print("=== All tests completed successfully! ===")
        print()
        
        # Ask user if they want to cleanup
        cleanup = input("Do you want to cleanup test data? (y/n): ")
        if cleanup.lower() == 'y':
            cleanup_test_data()
            
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
