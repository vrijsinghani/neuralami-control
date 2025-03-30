#!/usr/bin/env python
import os
import sys
import django
import logging

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.agents.utils.crawl_url import crawl_url

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define scrape options
scrape_options = {
    "formats": ["html", "markdown"],
    "onlyMainContent": True,
    "timeout": 30000,
    "removeBase64Images": True,
    "blockAds": True,
}

logger.info("Starting FireCrawl test")

# Call the crawl_url function
try:
    result = crawl_url(
        url="https://crazygatorairboats.com",
        limit=15,
        max_depth=10,
        ignore_sitemap=False,
        ignore_query_parameters=False,
        scrape_options=scrape_options,
        include_html=True,
        include_markdown=True,
        wait_for_completion=True,
        poll_interval=10
    )
    
    # Print the result
    if result:
        logger.info(f"Crawl completed successfully: {result.get('success', False)}")
        logger.info(f"Total pages: {result.get('total_pages', 0)}")
        logger.info(f"Credits used: {result.get('credits_used', 0)}")
        
        # Print information about each page
        pages = result.get('pages', [])
        logger.info(f"Number of pages in result: {len(pages)}")
        
        for i, page in enumerate(pages):
            page_url = page.get('url', 'No URL')
            page_title = page.get('title', 'No title')
            content = page.get('content', '')
            text_content = page.get('textContent', '')
            excerpt = page.get('excerpt', 'No excerpt')
            
            logger.info(f"--- Page {i+1}: {page_url} ---")
            logger.info(f"  Title: {page_title}")
            logger.info(f"  Content length: {len(content)}")
            logger.info(f"  TextContent length: {len(text_content)}")
            logger.info(f"  Excerpt: {excerpt[:100]}...")
            # Log the beginning of the actual content
            logger.info(f"  Content (HTML Preview):\n{content[:1500]}...")
            logger.info(f"  TextContent (Markdown Preview):\n{text_content[:500]}...")
            logger.info(f"---------------------------------------")
            
    else:
        logger.error("Crawl failed or returned no results")
except Exception as e:
    logger.error(f"Error during test: {str(e)}", exc_info=True)