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
            logger.debug(f"Progress callback called with data: {data}")
            
            # Store update in cache with ID
            cache.set(
                f"{cache_key}_{last_update_id}",
                data,
                timeout=3600  # 1 hour timeout
            )
            # Store latest update ID
            cache.set(cache_key, last_update_id, timeout=3600)
            
            #logger.debug(f"Stored update {last_update_id} in cache")
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
    """Process audit updates from cache and send to websocket."""
    logger.info(f"Starting update processor for audit {audit_id}")
    
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
                    #logger.debug(f"Processing update {last_processed_id} for audit {audit_id}")
                    async_to_sync(channel_layer.group_send)(
                        audit_group,
                        {
                            'type': 'audit.update',
                            'data': update
                        }
                    )
            
            # Only check completion after processing all available updates
            if should_stop or (cache.get(f"{cache_key}_complete") or cache.get(f"{cache_key}_error")):
                if last_processed_id >= latest_id:  # Only stop if we've processed everything
                    # Send completion message with results
                    try:
                        audit = SEOAuditResult.objects.get(id=audit_id)
                        if audit.status == 'completed' and audit.results:
                            # Create SEOAuditIssue records
                            
                            # Process meta tag issues
                            for meta_issue in audit.results.get('meta_tag_issues', []):
                                for issue in meta_issue.get('issues', []):
                                    SEOAuditIssue.objects.create(
                                        audit=audit,
                                        severity='high' if issue['type'] == 'title' else 'medium',
                                        issue_type=issue['type'],
                                        url=meta_issue['url'],
                                        details=issue,
                                        discovered_at=timezone.now()
                                    )
                            
                            # Process image issues
                            for page_images in audit.results.get('image_issues', []):
                                for img_issue in page_images.get('images', []):
                                    for issue in img_issue.get('issues', []):
                                        SEOAuditIssue.objects.create(
                                            audit=audit,
                                            severity=issue.get('severity', 'medium'),
                                            issue_type=f"image_{issue['type']}",
                                            url=page_images['page_url'],
                                            details=f"{issue['issue']} - {img_issue.get('url', '')}",
                                            discovered_at=timezone.now()
                                        )

                            # Process content issues
                            for content_issue in audit.results.get('content_issues', []):
                                for issue in content_issue.get('issues', []):
                                    SEOAuditIssue.objects.create(
                                        audit=audit,
                                        severity=issue.get('severity', 'medium'),
                                        issue_type=issue['type'],
                                        url=content_issue['url'],
                                        details=issue['issue'],
                                        discovered_at=timezone.now()
                                    )

                            # Process social media issues
                            for social_issue in audit.results.get('social_media_issues', []):
                                for issue in social_issue.get('issues', []):
                                    SEOAuditIssue.objects.create(
                                        audit=audit,
                                        severity=issue.get('severity', 'medium'),
                                        issue_type=issue['type'],
                                        url=social_issue['url'],
                                        details=issue['issue'],
                                        discovered_at=timezone.now()
                                    )

                            # Process canonical issues
                            for canonical_issue in audit.results.get('canonical_issues', []):
                                for issue in canonical_issue.get('issues', []):
                                    SEOAuditIssue.objects.create(
                                        audit=audit,
                                        severity=issue.get('severity', 'medium'),
                                        issue_type=issue['type'],
                                        url=canonical_issue['url'],
                                        details=issue['issue'],
                                        discovered_at=timezone.now()
                                    )

                            # Process sitemap validation issues
                            sitemap_data = audit.results.get('sitemap', {})
                            for issue in sitemap_data.get('issues', []):
                                SEOAuditIssue.objects.create(
                                    audit=audit,
                                    severity=issue.get('severity', 'high'),
                                    issue_type=issue['type'],
                                    url=issue.get('url', audit.website),
                                    details=issue['issue'],
                                    discovered_at=timezone.now()
                                )
                            
                            # Process broken links
                            for link in audit.results.get('broken_links', []):
                                SEOAuditIssue.objects.create(
                                    audit=audit,
                                    severity='critical',
                                    issue_type='broken_link',
                                    url=link['source_url'],
                                    details={
                                        'target_url': link['target_url'],
                                        'status_code': link.get('status_code'),
                                        'error': link.get('error', 'Not accessible')
                                    },
                                    discovered_at=timezone.now()
                                )
                            
                            # Process duplicate content
                            for dup in audit.results.get('duplicate_content', []):
                                SEOAuditIssue.objects.create(
                                    audit=audit,
                                    severity='medium',
                                    issue_type='duplicate_content',
                                    url=dup['urls'][0],  # Use first URL as primary
                                    details={
                                        'duplicate_urls': dup['urls'][1:],
                                        'similarity': dup['similarity']
                                    },
                                    discovered_at=timezone.now()
                                )

                            # Process SSL issues
                            ssl_issues = audit.results.get('ssl_issues', {})
                            if ssl_issues and not ssl_issues.get('valid_certificate'):
                                SEOAuditIssue.objects.create(
                                    audit=audit,
                                    severity='critical',
                                    issue_type='ssl_issue',
                                    url=audit.website,
                                    details={'error': 'Invalid SSL certificate'},
                                    discovered_at=timezone.now()
                                )

                            # Process sitemap issues
                            if not audit.results.get('sitemap_present'):
                                SEOAuditIssue.objects.create(
                                    audit=audit,
                                    severity='high',
                                    issue_type='missing_sitemap',
                                    url=audit.website,
                                    details={'error': 'Missing sitemap.xml'},
                                    discovered_at=timezone.now()
                                )

                            # Format results for frontend
                            formatted_results = {
                                'issues': []
                            }
                            
                            # Get all issues from database
                            for issue in audit.issues.all():
                                formatted_results['issues'].append({
                                    'severity': issue.severity,
                                    'issue_type': issue.issue_type,
                                    'url': issue.url,
                                    'details': issue.details,
                                    'discovered_at': issue.discovered_at.isoformat()
                                })
                            
                            # Add summary stats
                            formatted_results['summary'] = audit.results.get('summary', {})
                            
                            # Send completion message with results
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
                            logger.debug(f"Sent completion message with results for audit {audit_id}")
                        elif audit.status == 'failed':
                            # Send error message
                            async_to_sync(channel_layer.group_send)(
                                audit_group,
                                {
                                    'type': 'audit.error',
                                    'error': audit.error or "Unknown error occurred"
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error sending completion message: {str(e)}")
                    
                    logger.info(f"Audit {audit_id} finished, stopping update processor")
                    break
                should_stop = True  # Mark for stopping after processing remaining updates
            
            # Sleep briefly before next check
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error processing updates for audit {audit_id}: {str(e)}")
            break
    
    logger.info(f"Update processor finished for audit {audit_id}") 