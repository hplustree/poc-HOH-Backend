#!/usr/bin/env python3
"""
Script to create PostgreSQL database if it doesn't exist.
This script reads database configuration from Django settings and creates the database.
"""

import os
import sys
import django
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hoh_project.settings')
django.setup()

from django.conf import settings

def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    
    db_config = settings.DATABASES['default']
    db_name = db_config['NAME']
    db_user = db_config['USER']
    db_password = db_config['PASSWORD']
    db_host = db_config['HOST']
    db_port = db_config['PORT']
    
    print(f"Checking if database '{db_name}' exists...")
    
    try:
        # Connect to PostgreSQL server (to 'postgres' database)
        conn = psycopg2.connect(
            dbname='postgres',
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        exists = cursor.fetchone()
        
        if exists:
            print(f"✓ Database '{db_name}' already exists.")
        else:
            # Create database
            print(f"Creating database '{db_name}'...")
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(db_name)
                )
            )
            print(f"✓ Database '{db_name}' created successfully!")
        
        cursor.close()
        conn.close()
        
        return True
        
    except psycopg2.Error as e:
        print(f"✗ Error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    success = create_database_if_not_exists()
    sys.exit(0 if success else 1)
