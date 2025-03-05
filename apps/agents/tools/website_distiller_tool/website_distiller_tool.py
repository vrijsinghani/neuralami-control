import logging
from typing import Type
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from apps.agents.utils.scrape_url import scrape_url
from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool
from apps.agents.tools.compression_tool.compression_tool import CompressionTool
import json
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

class WebsiteDistillerToolSchema(BaseModel):
    """Input schema for WebsiteDistillerTool."""
    website_url: str = Field(..., description="The website URL to crawl and process")
    max_tokens: int = Field(default=16384, description="Maximum number of tokens in the processed output")
    detail_level: str = Field(
        default="comprehensive",
        description="Detail level: 'comprehensive' (preserve all details), 'detailed' (preserve most details), or 'focused' (key details only)"
    )
    user_id: int = Field(..., description="ID of the user initiating the crawl")
    max_pages: int = Field(default=1, description="Maximum number of pages to crawl (if 1, uses direct scraping)")
    max_depth: int = Field(default=1, description="Maximum depth for crawling")

    model_config = {
        "extra": "forbid"
    }

class WebsiteDistillerTool(BaseTool):
    """
    Crawls a website to extract its content, then processes and organizes the content while preserving important information.
    Combines website crawling with advanced NLP processing for comprehensive content analysis (comprehensive, detailed, or focused)
    """
    name: str = "Website Content Distillation Tool"
    description: str = """
    Crawls a website to extract its content, then processes and organizes the content while preserving important information.
    Combines website crawling with advanced NLP processing for comprehensive content analysis.
    """
    args_schema: Type[BaseModel] = WebsiteDistillerToolSchema

    def _run(
        self,
        website_url: str,
        user_id: int,
        max_tokens: int = 16384,
        detail_level: str = "comprehensive",
        max_pages: int = 10,
        max_depth: int = 3
    ) -> str:
        try:
            # Step 1: Normalize the URL
            parsed = urlparse(website_url)
            normalized_url = urlunparse((
                parsed.scheme or 'https',  # Default to https if no scheme
                parsed.netloc.lower(),
                parsed.path.rstrip('/'),  # Remove trailing slashes
                '',
                parsed.query,
                ''
            ))
            
            # Step 2: Choose method based on max_pages
            logger.info(f"Starting website content extraction for: {normalized_url}, max_pages={max_pages}")
            
            raw_content = None
            result_data = None
            
            if max_pages == 1:
                # Use direct scraping for single page
                logger.info(f"Using direct scrape_url for single page: {normalized_url}")
                try:
                    # Use scrape_url for single page extraction
                    scrape_result = scrape_url(
                        url=normalized_url,
                        cache=True,
                        stealth=True,
                        timeout=60000
                    )
                    
                    if not scrape_result:
                        logger.error(f"Direct scraping failed for URL: {normalized_url}")
                        return json.dumps({
                            "error": "Scraping failed",
                            "message": "Could not fetch content from the provided URL"
                        })
                    
                    # Extract content - check for 'text' field which is what direct scraping returns
                    raw_content = scrape_result.get("text", scrape_result.get("textContent", scrape_result.get("content", "")))
                    
                    # Create similar structure to multi-page result
                    result_data = {
                        "status": "success",
                        "results": [scrape_result],
                        "total_pages": 1
                    }
                    
                except Exception as e:
                    logger.error(f"Error during direct scraping: {str(e)}")
                    return json.dumps({
                        "error": "Scraping failed",
                        "message": str(e)
                    })
            else:
                # Use WebCrawlerTool for multi-page crawling
                logger.info(f"Using WebCrawlerTool for multi-page crawl: {normalized_url}")
                try:
                    web_crawler_tool = WebCrawlerTool()
                    
                    # Crawl multiple pages
                    crawl_result = web_crawler_tool._run(
                        start_url=normalized_url,
                        user_id=user_id,
                        max_pages=max_pages,
                        max_depth=max_depth,
                        output_format="text,metadata",  # Get text and metadata
                        stay_within_domain=True
                    )
                    
                    # Parse the crawl result
                    result_data = json.loads(crawl_result)
                    if result_data.get("status") != "success":
                        logger.error(f"Crawl failed: {result_data.get('message', 'Unknown error')}")
                        return json.dumps({
                            "error": "Crawling failed",
                            "message": result_data.get("message", "Unknown error")
                        })
                    
                    # Get the content from results
                    results = result_data.get("results", [])
                    if not results:
                        return json.dumps({
                            "error": "No content found",
                            "message": "The crawl returned no results"
                        })
                    
                    # Combine content from all pages with page titles as headers
                    combined_content = []
                    for page_result in results:
                        page_url = page_result.get("url", "")
                        page_title = page_result.get("title", page_url)
                        # Look for content in 'text' field first, which is what WebCrawlerTool returns
                        page_content = page_result.get("text", page_result.get("textContent", page_result.get("content", "")))
                        
                        if page_content:
                            combined_content.append(f"# {page_title}\n\n{page_content}\n\n")
                    
                    raw_content = "\n".join(combined_content)
                    
                except Exception as e:
                    logger.error(f"Error during multi-page crawl: {str(e)}")
                    return json.dumps({
                        "error": "Crawling failed",
                        "message": str(e)
                    })
            
            if not raw_content:
                return json.dumps({
                    "error": "No content found",
                    "message": "The extraction process returned no content"
                })

            # Step 3: Process the content
            logger.info("Processing extracted content")
            compression_tool = CompressionTool()
            processed_result = compression_tool._run(
                content=raw_content,
                max_tokens=max_tokens,
                detail_level=detail_level
            )

            # Parse the compression tool result
            compression_data = json.loads(processed_result)
            
            # Format the final result
            result = {
                'processed_content': compression_data.get('processed_content', ''),
                'source_url': normalized_url,
                'crawl_result_id': result_data.get('crawl_result_id'),
                'total_pages': result_data.get('total_pages', 0),
                'timestamp': result_data.get('timestamp', '')
            }
            
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error in WebsiteDistillerTool: {str(e)}")
            return json.dumps({
                "error": "Processing failed",
                "message": str(e)
            })
