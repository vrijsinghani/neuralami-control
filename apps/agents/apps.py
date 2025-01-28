from django.apps import AppConfig
import os
import logging
import sys
from django.conf import settings

logger = logging.getLogger(__name__)

class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agents'
    verbose_name = 'CrewAI Agents'
    
    def ready(self):
        """Initialize the Slack bot only once under Daphne"""
        # Get the current process name
        process_name = sys.argv[0] if sys.argv else ''
        #logger.info(f"AgentsConfig.ready() called with process_name: {process_name}")
        #logger.info(f"RUN_MAIN: {os.environ.get('RUN_MAIN')}")
        #logger.info(f"Already initialized: {getattr(self, '_slack_initialized', False)}")
        
        # Only initialize if:
        # 1. We're running under Daphne
        # 2. We haven't already initialized in this process
        # 3. We're not in an auto-reload cycle
        if ('daphne' not in process_name or 
            getattr(self, '_slack_initialized', False) or
            os.environ.get('RUN_MAIN') == 'true'):
            logger.info("Skipping Slack bot initialization due to conditions not met")
            return
            
        #logger.info("All conditions met, proceeding with Slack bot initialization...")
        
        try:
            from .integrations.slack_bot import start_slack_bot
            start_slack_bot()
            self._slack_initialized = True
            logger.info("Slack bot initialization completed and flag set")
        except Exception as e:
            logger.error(f"Failed to initialize Slack bot: {e}", exc_info=True)
