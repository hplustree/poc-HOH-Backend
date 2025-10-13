from django.urls import path
from . import views

urlpatterns = [
    # Existing endpoints
    path('projects/', views.create_project, name='create_project'),
    path('projects/list/', views.list_projects, name='list_projects'),
    path('project-costs/', views.create_project_cost, name='create_project_cost'),
    path('project-costs/list/', views.list_project_costs, name='list_project_costs'),
    path('project-overheads/', views.create_project_overhead, name='create_project_overhead'),
    path('project-overheads/list/', views.list_project_overheads, name='list_project_overheads'),
    
    # New version control endpoints
    path('projects/<int:project_id>/latest/', views.get_project_latest_data, name='get_project_latest_data'),
    path('project-costs/<int:cost_id>/versions/', views.get_project_cost_versions, name='get_project_cost_versions'),
    path('project-overheads/<int:overhead_id>/versions/', views.get_project_overhead_versions, name='get_project_overhead_versions'),
    path('project-costs/<int:cost_id>/', views.update_project_cost, name='update_project_cost'),
    path('project-overheads/<int:overhead_id>/', views.update_project_overhead, name='update_project_overhead'),
]
