import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
if os.environ.get('DJANGO_SETTINGS_MODULE'):

    app = Celery('core')

    app.config_from_object('django.conf:settings', namespace='CELERY')

    # Load task modules from all registered Django apps.
    app.autodiscover_tasks()

else:
    print(' ')
    print('Celery Configuration ERROR: ') 
    print('  > "DJANGO_SETTINGS_MODULE" not set in environment (value in manage.py)')
    print('  Hint: export DJANGO_SETTINGS_MODULE=project.settings ') 
    print(' ')
  
app = Celery('seoclientmanager')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.

# Load task modules from all registered Django apps.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@app.task(bind=True)
def debug_task(self):
  print(f'Request: {self.request!r}')