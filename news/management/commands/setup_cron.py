import os
import subprocess
from django.core.management.base import BaseCommand
from django.conf import settings
from dotenv import load_dotenv


load_dotenv()
class Command(BaseCommand):
    help = 'Setup cron job for daily news processing at 3 AM every day'

    def handle(self, *args, **options):
        """
        Sets up the cron job using timing from environment variables
        """
        try:
            if options.get('remove'):
                self.remove_cron_job()
                return
                
            # Get cron time from environment variable
            cron_time = self.get_cron_time_from_env()
            
            # Get project path
            project_path = os.getcwd()
            
            # Find Python executable
            python_path = self.find_python_executable(project_path)
            
            # Create logs directory if it doesn't exist
            logs_dir = os.path.join(project_path, 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            # Create cron job command with proper logging
            log_file = os.path.join(logs_dir, 'daily_news_processor.log')
            cron_command = f"{cron_time} cd {project_path} && {python_path} manage.py daily_news_processor >> {log_file} 2>&1"
            
            self.stdout.write(
                self.style.SUCCESS('Setting up cron job for daily news processing...')
            )
            self.stdout.write(f'Schedule: {self.format_cron_time(cron_time)} ({cron_time})')
            self.stdout.write(f'Project: {project_path}')
            self.stdout.write(f'Python: {python_path}')
            self.stdout.write(f'Logs: {log_file}')
            
            # Get current crontab
            try:
                current_crontab = subprocess.check_output(['crontab', '-l'], stderr=subprocess.DEVNULL, text=True)
            except subprocess.CalledProcessError:
                current_crontab = ""
            
            # Remove existing daily_news_processor entries
            lines = current_crontab.split('\n')
            filtered_lines = [line for line in lines if 'daily_news_processor' not in line and line.strip()]
            
            # Add new cron job
            filtered_lines.append(cron_command)
            
            # Write new crontab
            new_crontab = '\n'.join(filtered_lines) + '\n'
            
            # Set the new crontab
            process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
            process.communicate(input=new_crontab)
            
            if process.returncode == 0:
                self.stdout.write(
                    self.style.SUCCESS('Cron job successfully configured!')
                )
                self.stdout.write(f'The job will run {self.format_cron_time(cron_time)}')
                self.stdout.write('Check logs for execution details')
                
                # Show current crontab
                self.stdout.write('\nCurrent cron jobs:')
                try:
                    subprocess.run(['crontab', '-l'], check=True)
                except subprocess.CalledProcessError:
                    self.stdout.write('No cron jobs found')
                    
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to set up cron job')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error setting up cron job: {str(e)}')
            )

    def find_python_executable(self, project_path):
        """Find the appropriate Python executable"""
        # Try virtual environment first
        venv_python = os.path.join(project_path, 'venv', 'bin', 'python')
        if os.path.exists(venv_python):
            return venv_python
            
        # Try system python3
        try:
            python_path = subprocess.check_output(['which', 'python3'], text=True).strip()
            return python_path
        except subprocess.CalledProcessError:
            pass
            
        # Fallback to python
        try:
            python_path = subprocess.check_output(['which', 'python'], text=True).strip()
            return python_path
        except subprocess.CalledProcessError:
            return 'python'

    def remove_cron_job(self):
        """Remove the daily news processor cron job"""
        try:
            # Get current crontab
            try:
                current_crontab = subprocess.check_output(['crontab', '-l'], stderr=subprocess.DEVNULL, text=True)
            except subprocess.CalledProcessError:
                self.stdout.write(
                    self.style.WARNING('No existing cron jobs found')
                )
                return
            
            # Remove daily_news_processor entries
            lines = current_crontab.split('\n')
            filtered_lines = [line for line in lines if 'daily_news_processor' not in line and line.strip()]
            
            # Write new crontab
            new_crontab = '\n'.join(filtered_lines) + '\n' if filtered_lines else ''
            
            process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
            process.communicate(input=new_crontab)
            
            if process.returncode == 0:
                self.stdout.write(
                    self.style.SUCCESS('Cron job removed successfully!')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to remove cron job')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error removing cron job: {str(e)}')
            )

    def get_cron_time_from_env(self):
        """Get cron time from environment variable"""
        # Try environment variable
        cron_time = os.getenv('DAILY_NEWS_CRON_TIME')
        
        if not cron_time:
            # Default fallback to 3 AM
            cron_time = "0 3 * * *"
            self.stdout.write(
                self.style.WARNING('WARNING: DAILY_NEWS_CRON_TIME not found, using default: 3:00 AM')
            )
        else:
            self.stdout.write(f'Using cron time from environment: {cron_time}')
            
        return cron_time

    def format_cron_time(self, cron_time):
        """Convert cron time to human readable format"""
        try:
            parts = cron_time.split()
            if len(parts) >= 2:
                minute = parts[0]
                hour = parts[1]
                
                # Convert to 12-hour format
                hour_int = int(hour)
                if hour_int == 0:
                    return f"every day at 12:{minute.zfill(2)} AM"
                elif hour_int < 12:
                    return f"every day at {hour_int}:{minute.zfill(2)} AM"
                elif hour_int == 12:
                    return f"every day at 12:{minute.zfill(2)} PM"
                else:
                    return f"every day at {hour_int-12}:{minute.zfill(2)} PM"
            else:
                return f"with schedule: {cron_time}"
        except (ValueError, IndexError):
            return f"with schedule: {cron_time}"

    def add_arguments(self, parser):
        parser.add_argument(
            '--remove',
            action='store_true',
            help='Remove the cron job instead of setting it up',
        )
