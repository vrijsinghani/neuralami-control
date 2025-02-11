import logging
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
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

    model_config = {
        "extra": "forbid"
    }

class WebsiteDistillerTool(BaseTool):
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
        max_pages: int = 10
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
            
            # Step 2: Crawl the website using CrawlWebsiteTool
            logger.info(f"Starting website crawl for: {normalized_url}")
            crawl_tool = CrawlWebsiteTool()
            
            try:
                # Crawl multiple pages with markdown output
                crawl_result = crawl_tool._run(
                    website_url=normalized_url,
                    user_id=user_id,
                    max_pages=max_pages,
                    max_depth=3,  # Allow reasonable depth for content gathering
                    output_type="markdown"  # Get markdown formatted content
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
                if not results or not results[0].get("content"):
                    return json.dumps({
                        "error": "No content found",
                        "message": "The crawl returned no results"
                    })
                
                # Get the combined content from the first result
                content = results[0].get("content")

            except Exception as e:
                logger.error(f"Error during crawl: {str(e)}")
                return json.dumps({
                    "error": "Crawling failed",
                    "message": str(e)
                })

            # Step 3: Process the content
            logger.info("Processing crawled content")
            compression_tool = CompressionTool()
            processed_result = compression_tool._run(
                content=content,
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
