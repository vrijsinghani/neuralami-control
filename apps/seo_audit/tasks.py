import time
import json
import logging
from celery import shared_task, current_app
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.cache import cache
from apps.seo_audit.models import SEOAuditResult, SEOAuditIssue
from apps.agents.tools.seo_audit_tool.seo_audit_tool import SEOAuditTool
from django.utils import timezone
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_seo_audit(self, audit_id, website, max_pages=100, check_external_links=False, crawl_delay=1.0):
    """Run SEO audit task."""
    logger.info(f"Starting SEO audit task for audit_id: {audit_id}, group: audit_{audit_id}")
    
    # Get the channel layer
    channel_layer = get_channel_layer()
    audit_group = f'audit_{audit_id}'
    
    # Use cache as message bus
    cache_key = f"seo_audit_progress_{audit_id}"
    last_update_id = 0

    def progress_callback(data):
        """Progress callback that uses cache as message bus"""
        try:
            nonlocal last_update_id
            last_update_id += 1
            
            # Store update in cache with ID
            cache.set(
                f"{cache_key}_{last_update_id}",
                data,
                timeout=3600  # 1 hour timeout
            )
            # Store latest update ID
            cache.set(cache_key, last_update_id, timeout=3600)
            
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

    try:
        # Update audit status to running
        audit = SEOAuditResult.objects.get(id=audit_id)
        audit.status = 'running'
        audit.save()

        # Start SEO audit
        logger.info(f"Running audit tool for {website}")
        audit_tool = SEOAuditTool()
        
        # Start background task to process updates using current Celery app
        current_app.send_task(
            'apps.seo_audit.tasks.process_audit_updates',
            args=[audit_id, cache_key],
            countdown=1  # Start after 1 second
        )
        
        # Run the audit
        results = audit_tool._run(
            website=website,
            max_pages=max_pages,
            check_external_links=check_external_links,
            crawl_delay=crawl_delay,
            progress_callback=progress_callback
        )

        # Save results
        audit.results = results
        audit.status = 'completed'
        # Set end_time instead of trying to set duration directly
        audit.end_time = timezone.now()
        audit.save()

        # Store completion marker
        cache.set(f"{cache_key}_complete", True, timeout=3600)
        
        return {
            'status': 'success',
            'audit_id': audit_id
        }

    except Exception as e:
        logger.error(f"Error running SEO audit: {str(e)}")
        audit = SEOAuditResult.objects.get(id=audit_id)
        audit.status = 'failed'
        audit.error = str(e)
        audit.save()
        
        # Store error marker
        cache.set(f"{cache_key}_error", str(e), timeout=3600)
        raise

@shared_task(bind=True)
def process_audit_updates(self, audit_id, cache_key):
    """Process SEO audit updates from cache and send to WebSocket."""
    
    channel_layer = get_channel_layer()
    audit_group = f'audit_{audit_id}'
    last_processed_id = 0
    should_stop = False
    
    while True:
        try:
            # Get latest update ID
            latest_id = cache.get(cache_key, 0)
            
            # Process any new updates
            while last_processed_id < latest_id:
                last_processed_id += 1
                update = cache.get(f"{cache_key}_{last_processed_id}")
                
                if update:
                    async_to_sync(channel_layer.group_send)(
                        audit_group,
                        {
                            'type': 'audit.update',
                            'data': update
                        }
                    )
            
            # Check if audit is complete
            if should_stop or (cache.get(f"{cache_key}_complete") or cache.get(f"{cache_key}_error")):
                if last_processed_id >= latest_id:  # Only stop if we've processed everything
                    try:
                        audit = SEOAuditResult.objects.get(id=audit_id)
                        if audit.status == 'completed' and audit.results:
                            logger.info(f"Processing issues for completed audit {audit_id}")
                            
                            # Clear existing issues
                            SEOAuditIssue.objects.filter(audit=audit).delete()
                            
                            try:
                                # Store all issues
                                for issue in audit.results.get('issues', []):
                                    # Ensure issue_type has a default value if not present
                                    issue_type = issue.get('type')
                                    if not issue_type:
                                        # Try to determine issue type from the issue details
                                        if 'ssl' in str(issue.get('issue', '')).lower():
                                            issue_type = 'ssl_error'
                                        elif 'link' in str(issue.get('issue', '')).lower():
                                            issue_type = 'broken_link'
                                        elif 'meta' in str(issue.get('issue', '')).lower():
                                            issue_type = 'meta_tag_issue'
                                        elif 'content' in str(issue.get('issue', '')).lower():
                                            issue_type = 'content_issue'
                                        else:
                                            issue_type = 'general_issue'  # Default fallback
                                    
                                    SEOAuditIssue.objects.create(
                                        audit=audit,
                                        severity=issue.get('severity', 'medium'),
                                        issue_type=issue_type,
                                        url=issue.get('url', audit.website),
                                        details=issue,
                                        discovered_at=timezone.now()
                                    )
                                
                                logger.info(f"Successfully processed {len(audit.results.get('issues', []))} issues for audit {audit_id}")
                                
                            except Exception as e:
                                logger.error(f"Error processing issues: {str(e)}", exc_info=True)
                                raise
                            
                            # Send completion message
                            formatted_results = {
                                'issues': [
                                    {
                                        'severity': issue.severity,
                                        'issue_type': issue.issue_type,
                                        'url': issue.url,
                                        'details': issue.details,
                                        'discovered_at': issue.discovered_at.isoformat()
                                    }
                                    for issue in audit.issues.all()
                                ],
                                'summary': audit.results.get('summary', {})
                            }
                            
                            async_to_sync(channel_layer.group_send)(
                                audit_group,
                                {
                                    'type': 'audit.complete',
                                    'data': {
                                        'results': formatted_results,
                                        'status': 'completed'
                                    }
                                }
                            )
                            logger.info(f"Sent completion message for audit {audit_id}")
                            
                        elif audit.status == 'failed':
                            async_to_sync(channel_layer.group_send)(
                                audit_group,
                                {
                                    'type': 'audit.error',
                                    'error': audit.error or "Unknown error occurred"
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error processing completion: {str(e)}", exc_info=True)
                        raise
                    
                    logger.info(f"Audit {audit_id} finished, stopping update processor")
                    break
                should_stop = True
            
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in update processor for audit {audit_id}: {str(e)}", exc_info=True)
            break
    
    logger.info(f"Update processor finished for audit {audit_id}") 