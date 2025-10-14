# Generated manually to remove budget app tables

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_userdetail_is_active'),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS project_cost_versions CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS project_overhead_versions CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS project_versions CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS project_costs CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS project_overheads CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS projects CASCADE;",
            reverse_sql="-- Cannot reverse this migration"
        ),
    ]
