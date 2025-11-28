from django.db import migrations
import uuid

def populate_project_id(apps, schema_editor):
    Projects = apps.get_model('budget', 'Projects')
    for project in Projects.objects.all():
        if project.project_id is None:
            project.project_id = uuid.uuid4()
            project.save(update_fields=['project_id'])

class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0005_projects_project_id'),
    ]

    operations = [
        migrations.RunPython(populate_project_id, migrations.RunPython.noop),
    ]