from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from .models import SEOAuditResult, SEOAuditIssue
from apps.agents.tools.seo_audit_tool.seo_audit_tool import SEOAuditTool
import logging
import asyncio

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_seo_audit(self, audit_id, website, max_pages=100, check_external_links=False, crawl_delay=1.0):
    """Run SEO audit task."""
    logger.info(f"Starting SEO audit task for audit_id: {audit_id}, group: audit_{audit_id}")
    
    # Get the channel layer
    channel_layer = get_channel_layer()
    audit_group = f'audit_{audit_id}'

    async def async_progress_callback(data):
        """Async progress callback"""
        try:
            logger.debug(f"Progress callback called with data: {data}")
            websocket_type = 'audit.update'  # Use dot notation for frontend
            await channel_layer.group_send(
                audit_group,
                {
                    'type': websocket_type,
                    'data': data
                }
            )
            logger.debug(f"Sent {websocket_type} message: {data}")
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

    # Create a sync wrapper for the async callback
    def progress_callback(data):
        """Sync wrapper for progress callback"""
        try:
            # Instead of creating/getting event loop here, use asyncio.run()
            # This ensures we have a clean event loop for each callback
            asyncio.run(async_progress_callback(data))
        except Exception as e:
            logger.error(f"Error in progress callback wrapper: {str(e)}")
            # If asyncio.run() fails, try using create_task directly
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an event loop, just await directly
                    loop.create_task(async_progress_callback(data))
                else:
                    # If no loop is running, run until complete
                    loop.run_until_complete(async_progress_callback(data))
            except Exception as e2:
                logger.error(f"Fallback error in progress callback: {str(e2)}")

    try:
        # Update audit status to running
        audit = SEOAuditResult.objects.get(id=audit_id)
        audit.status = 'running'
        audit.save()

        logger.info(f"Running audit tool for {website}")
        audit_tool = SEOAuditTool()
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

        # Format and send completion message
        formatted_results = {
            'issues': []
        }
        
        # Format meta tag issues
        for meta_issue in results.get('meta_tag_issues', []):
            for issue in meta_issue.get('issues', []):
                formatted_results['issues'].append({
                    'severity': 'high' if issue['type'] == 'title' else 'medium',
                    'issue_type': issue['type'],
                    'url': meta_issue['url'],
                    'details': issue['issue'],
                    'discovered_at': results['summary']['end_time']
                })
        
        # Format broken links
        for link in results.get('broken_links', []):
            formatted_results['issues'].append({
                'severity': 'critical',
                'issue_type': 'broken_link',
                'url': link['source_url'],
                'details': f"Broken link to {link['target_url']}: {link.get('error', 'Not accessible')}",
                'discovered_at': link.get('timestamp', results['summary']['end_time'])
            })
        
        # Format duplicate content
        for dup in results.get('duplicate_content', []):
            formatted_results['issues'].append({
                'severity': 'medium',
                'issue_type': 'duplicate_content',
                'url': dup['url1'],
                'details': f"Content duplicated with {dup['url2']} (similarity: {dup['similarity']}%)",
                'discovered_at': results['summary']['end_time']
            })

        # Add summary stats
        formatted_results['summary'] = results.get('summary', {})
        
        # Send completion message using asyncio.run()
        try:
            asyncio.run(channel_layer.group_send(
                audit_group,
                {
                    'type': 'audit.complete',
                    'data': {
                        'results': formatted_results,
                        'status': 'completed'
                    }
                }
            ))
        except RuntimeError:
            # If we're already in an event loop, use create_task
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(channel_layer.group_send(
                    audit_group,
                    {
                        'type': 'audit.complete',
                        'data': {
                            'results': formatted_results,
                            'status': 'completed'
                        }
                    }
                ))
            else:
                loop.run_until_complete(channel_layer.group_send(
                    audit_group,
                    {
                        'type': 'audit.complete',
                        'data': {
                            'results': formatted_results,
                            'status': 'completed'
                        }
                    }
                ))

        logger.info(f"Audit completed for {website}")

    except SEOAuditResult.DoesNotExist:
        logger.error(f"Audit record {audit_id} not found")
        raise

    except Exception as e:
        logger.error(f"Error running audit: {str(e)}")
        if 'audit' in locals():
            audit.status = 'failed'
            audit.error = str(e)
            audit.save()

            # Send error message using asyncio.run()
            try:
                asyncio.run(channel_layer.group_send(
                    audit_group,
                    {
                        'type': 'audit.error',
                        'error': str(e)
                    }
                ))
            except RuntimeError:
                # If we're already in an event loop, use create_task
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(channel_layer.group_send(
                        audit_group,
                        {
                            'type': 'audit.error',
                            'error': str(e)
                        }
                    ))
                else:
                    loop.run_until_complete(channel_layer.group_send(
                        audit_group,
                        {
                            'type': 'audit.error',
                            'error': str(e)
                        }
                    ))

    return {
        'status': audit.status if 'audit' in locals() else 'failed',
        'audit_id': audit_id
    } 