# In a file like core/management/commands/generate_version.py
import subprocess
import datetime
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Generate version information from git'

    def handle(self, *args, **options):
        try:
            # Get the current commit hash (works with uncommitted changes)
            commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
            
            try:
                # Try to get the latest git tag
                tag = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0']).decode().strip()
                # Get the commit count since that tag
                count = subprocess.check_output(['git', 'rev-list', f'{tag}..HEAD', '--count']).decode().strip()
                version = f"{tag}.{count}"
            except subprocess.CalledProcessError:
                # If no tags exist, use commit count as version
                count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD']).decode().strip()
                # Use date-based versioning as fallback
                today = datetime.datetime.now().strftime('%Y.%m.%d')
                version = f"{today}.{count}"
            
            # Write to a version.py file
            with open('core/version.py', 'w') as f:
                f.write(f"VERSION = '{version}'\n")
                f.write(f"COMMIT = '{commit}'\n")
                
            self.stdout.write(self.style.SUCCESS(f'Generated version: {version} ({commit})'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating version: {e}'))
            # Fallback version if git commands fail
            with open('core/version.py', 'w') as f:
                f.write("VERSION = '0.0.0'\n")
                f.write("COMMIT = 'unknown'\n")