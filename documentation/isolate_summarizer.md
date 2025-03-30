# Plan to Isolate Summarizer App

## Current Structure
- The summarizer functionality is currently part of the `seo_manager` app
- It uses views from `apps/seo_manager/views_summarizer.py` (summarize_view and task_status functions)
- It has templates in `templates/pages/apps/summarize.html`
- It uses models from `apps/seo_manager/models.py` (specifically SummarizerUsage model)
- It relies on tasks defined in `apps/tasks/tasks.py` (summarize_content task)
- It is mapped in URL routes in `apps/seo_manager/urls.py`

## Target Structure
- New app: `apps/summarizer/`
- New views: `apps/summarizer/views.py` containing the summarize_view and task_status functions
- New models: `apps/summarizer/models.py` containing the SummarizerUsage model
- New templates: `templates/pages/summarizer/summarize.html`
- New URL configuration: `apps/summarizer/urls.py` with routes for summarize_view and task_status
- Update to core URLs in `core/urls.py` to include the new app's URLs

## Implementation Steps

### 1. Create New App Structure
- Create directory `apps/summarizer/`
- Create required files:
  - `apps/summarizer/__init__.py`
  - `apps/summarizer/apps.py`
  - `apps/summarizer/models.py`
  - `apps/summarizer/views.py`
  - `apps/summarizer/urls.py`
  - `apps/summarizer/admin.py`
- Create templates directory:
  - `templates/pages/summarizer/`

### 2. Migrate Models
- Move `SummarizerUsage` model from `apps/seo_manager/models.py` to `apps/summarizer/models.py`:
  ```python
  from django.db import models
  from django.contrib.auth.models import User
  from django.utils import timezone

  class SummarizerUsage(models.Model):
      user = models.ForeignKey(User, on_delete=models.CASCADE)
      query = models.TextField()
      compressed_content = models.TextField()
      response = models.TextField()
      created_at = models.DateTimeField(auto_now_add=True)
      duration = models.DurationField()
      content_token_size = models.IntegerField()
      content_character_count = models.IntegerField()
      total_input_tokens = models.IntegerField()
      total_output_tokens = models.IntegerField()
      model_used = models.CharField(max_length=100)
  ```
- Setup admin.py to register the model:
  ```python
  from django.contrib import admin
  from .models import SummarizerUsage

  @admin.register(SummarizerUsage)
  class SummarizerUsageAdmin(admin.ModelAdmin):
      list_display = ('user', 'query', 'created_at', 'model_used')
      list_filter = ('model_used', 'created_at')
      search_fields = ('query', 'response')
      date_hierarchy = 'created_at'
  ```
- Create and apply migrations:
  ```
  python manage.py makemigrations summarizer
  python manage.py migrate
  ```

### 3. Migrate Views
- Move summarizer views from `apps/seo_manager/views_summarizer.py` to `apps/summarizer/views.py`
- Update import paths in the views:
  - Change `from apps.seo_manager.models import SummarizerUsage` to `from .models import SummarizerUsage`
  - Keep other imports the same

### 4. Migrate Templates
- Move `templates/pages/apps/summarize.html` to `templates/pages/summarizer/summarize.html`
- Update template:
  - Update form action URL from `{% url 'seo_manager:summarize_view' %}` to `{% url 'summarizer:summarize_view' %}`
  - Update task status URL from `{% url 'seo_manager:task_status' task_id="TASK_ID" %}` to `{% url 'summarizer:task_status' task_id="TASK_ID" %}`

### 5. Configure URLs
- Create `apps/summarizer/urls.py` with:
  ```python
  from django.urls import path
  from . import views

  app_name = 'summarizer'

  urlpatterns = [
      path('', views.summarize_view, name='summarize_view'),
      path('task_status/<str:task_id>/', views.task_status, name='task_status'),
  ]
  ```
- Update `core/urls.py` to include the new app's URLs:
  ```python
  path('summarize/', include('apps.summarizer.urls', namespace='summarizer')),
  ```
- Remove summarizer URLs from `apps/seo_manager/urls.py`:
  - Remove `path('summarize/', views_summarizer.summarize_view, name='summarize_view')`
  - Remove `path('task_status/<str:task_id>/', views_summarizer.task_status, name='task_status')`
  - Remove `from . import views_summarizer`

### 6. Update Django App Configuration
- Create `apps/summarizer/apps.py` with:
  ```python
  from django.apps import AppConfig

  class SummarizerConfig(AppConfig):
      name = 'apps.summarizer'
      verbose_name = 'Summarizer'
  ```
- Add the new app to `INSTALLED_APPS` in `core/settings.py`:
  ```python
  INSTALLED_APPS = [
      # ...existing apps...
      'apps.summarizer',
  ]
  ```

### 7. Update Task References
- Update `apps/tasks/tasks.py` to import SummarizerUsage from the new location:
  - Change `from apps.seo_manager.models import SummarizerUsage` to `from apps.summarizer.models import SummarizerUsage`

### 8. Create New App's __init__.py
- Create `apps/summarizer/__init__.py` (empty file)

### 9. Check for Additional Dependencies
- Search for other references to SummarizerUsage in the codebase:
  ```
  grep -r "SummarizerUsage" --include="*.py" .
  ```
- Update any additional files that reference SummarizerUsage

### 10. Testing
- Run Django development server
- Navigate to the new URL: `/summarize/`
- Test summarizer functionality to ensure it works as expected:
  - Submit a basic text for summarization
  - Submit a URL for summarization
  - Check that previous summarizations appear in the sidebar
- Check for any errors in logs

### 11. Cleanup
- After successful migration and testing, remove `views_summarizer.py` from seo_manager
- Remove the SummarizerUsage model from `apps/seo_manager/models.py`
- Add a redirect from the old URL to the new URL in `apps/seo_manager/urls.py` for backward compatibility (if needed)

## Potential Challenges
- Database migration: Ensure data is preserved when moving the model
- URL routing: Make sure old URLs redirect properly or update any hardcoded URLs in templates
- Dependency management: Other parts of the app might depend on the summarizer being in seo_manager
- Permission issues: Check if any permissions were tied to the old app structure

## Success Criteria
- Summarizer functionality is fully operational in its new location
- All templates render correctly
- API endpoints work as expected
- Admin interface works correctly
- No references to old locations remain in the codebase 