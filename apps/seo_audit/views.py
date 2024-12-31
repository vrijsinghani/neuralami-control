from django.views.generic import TemplateView, ListView, DetailView
from django.views.generic.edit import FormView
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.utils import timezone
import json
import csv
from io import StringIO
from celery.result import AsyncResult
import logging

from apps.seo_manager.models import Client
from .models import SEOAuditResult, SEOAuditIssue
from apps.agents.tools.seo_audit_tool.seo_audit_tool import SEOAuditTool
from .tasks import run_seo_audit

logger = logging.getLogger(__name__)

class AuditView(LoginRequiredMixin, TemplateView):
    template_name = 'seo_audit/audit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clients'] = Client.objects.filter(status='active').order_by('name')
        return context

class StartAuditView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            # Log the incoming request data
            logger.debug(f"Received audit request data: {request.body.decode()}")
            
            data = json.loads(request.body)
            client_id = data.get('client')
            website = data.get('website')
            max_pages = int(data.get('max_pages', 100))
            check_external_links = data.get('check_external_links', False)
            crawl_delay = float(data.get('crawl_delay', 1.0))

            # Validate required fields
            if not website:
                return JsonResponse({
                    'status': 'error',
                    'error': 'Website URL is required'
                }, status=400)

            # Create audit record
            audit = SEOAuditResult.objects.create(
                client_id=client_id if client_id else None,
                website=website,
                max_pages=max_pages,
                check_external_links=check_external_links,
                crawl_delay=crawl_delay,
                status='pending'
            )

            logger.info(f"Created audit record: {audit.id} for website: {website}")

            # Start Celery task
            task = run_seo_audit.delay(
                audit_id=audit.id,
                website=website,
                max_pages=max_pages,
                check_external_links=check_external_links,
                crawl_delay=crawl_delay
            )

            logger.info(f"Started Celery task: {task.id} for audit: {audit.id}")

            # Update audit with task ID
            audit.task_id = task.id
            audit.status = 'in_progress'
            audit.save()

            return JsonResponse({
                'status': 'success',
                'audit_id': audit.id,
                'task_id': task.id
            })

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON data'
            }, status=400)
        except ValueError as e:
            logger.error(f"Value error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': str(e)
            }, status=400)
        except Exception as e:
            logger.error(f"Error starting audit: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'error': str(e)
            }, status=500)

class GetAuditStatusView(LoginRequiredMixin, View):
    def get(self, request, audit_id, *args, **kwargs):
        audit = get_object_or_404(SEOAuditResult, id=audit_id)
        
        # Get task status if task_id exists
        task_status = None
        if audit.task_id:
            task = AsyncResult(audit.task_id)
            task_status = task.status

        return JsonResponse({
            'status': audit.status,
            'progress': audit.progress,
            'error': audit.error,
            'task_status': task_status
        })

class GetAuditResultsView(LoginRequiredMixin, DetailView):
    model = SEOAuditResult
    template_name = 'seo_audit/results.html'
    context_object_name = 'audit'
    pk_url_kwarg = 'audit_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        audit = self.object

        # Get severity distribution data
        severity_counts = audit.issues.values('severity').annotate(count=Count('id'))
        severity_data = {
            'labels': [item['severity'] for item in severity_counts],
            'values': [item['count'] for item in severity_counts]
        }

        # Get issue type distribution data
        type_counts = audit.issues.values('issue_type').annotate(count=Count('id'))
        issue_type_data = {
            'labels': [item['issue_type'] for item in type_counts],
            'values': [item['count'] for item in type_counts]
        }

        context.update({
            'severity_data': severity_data,
            'issue_type_data': issue_type_data,
            'severities': SEOAuditIssue.SEVERITY_CHOICES,
            'issue_types': SEOAuditIssue.ISSUE_TYPES
        })
        return context

class AuditHistoryView(LoginRequiredMixin, ListView):
    model = SEOAuditResult
    template_name = 'seo_audit/history.html'
    context_object_name = 'audits'
    paginate_by = 12
    ordering = ['-start_time']

class CancelAuditView(LoginRequiredMixin, View):
    def post(self, request, audit_id, *args, **kwargs):
        audit = get_object_or_404(SEOAuditResult, id=audit_id)
        
        if audit.task_id:
            # Revoke Celery task
            AsyncResult(audit.task_id).revoke(terminate=True)
        
        audit.status = 'cancelled'
        audit.end_time = timezone.now()
        audit.save()

        return JsonResponse({'status': 'success'})

class ExportAuditView(LoginRequiredMixin, View):
    def get(self, request, audit_id, *args, **kwargs):
        audit = get_object_or_404(SEOAuditResult, id=audit_id)
        
        # Create CSV file
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Severity',
            'Issue Type',
            'URL',
            'Details',
            'Discovered At'
        ])
        
        # Write issues
        for issue in audit.issues.all():
            writer.writerow([
                issue.get_severity_display(),
                issue.get_issue_type_display(),
                issue.url,
                json.dumps(issue.details),
                issue.discovered_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        # Prepare response
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="seo_audit_{audit_id}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        return response

class GetClientWebsiteView(LoginRequiredMixin, View):
    def get(self, request, client_id, *args, **kwargs):
        client = get_object_or_404(Client, id=client_id)
        return JsonResponse({
            'website_url': client.website_url
        }) 