import logging
import json
from typing import Type, Optional, Dict, Any, List, Literal, Union, ClassVar
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from crewai.tools import BaseTool
from django.conf import settings
from urllib.parse import urlparse

from apps.agents.utils.scrape_url import scrape_url, get_url_links

logger = logging.getLogger(__name__)

# Define output formats
class OutputType(str, Enum):
    HTML = "html"  # Raw HTML from full_content
    CLEANED_HTML = "cleaned_html"  # Cleaned HTML from content
    METADATA = "metadata"  # Metadata only
    TEXT = "text"  # Text content only
    LINKS = "links"  # Links only
    FULL = "full"  # All formats combined

class ScrapperToolSchema(BaseModel):
    """Input schema for ScrapperTool."""
    url: str = Field(..., description="URL to scrape")
    user_id: int = Field(..., description="ID of the user initiating the scrape")
    output_type: str = Field(
        default="text", 
        description="Type(s) of output content. Can be a single value (like 'text') or a comma-separated list with or without quotes (like 'metadata,links' or 'metadata','links')"
    )
    cache: bool = Field(
        default=True,
        description="Whether to use cached results if available"
    )
    stealth: bool = Field(
        default=True,
        description="Whether to use stealth mode"
    )
    timeout: int = Field(
        default=60000,
        description="Timeout in milliseconds"
    )
    device: str = Field(
        default="desktop",
        description="Device type to emulate (desktop, mobile, tablet, or specific device name)"
    )
    wait_until: str = Field(
        default="domcontentloaded",
        description="When to consider navigation successful (domcontentloaded, load, networkidle0, networkidle2)"
    )
    css_selector: Optional[str] = Field(
        default=None,
        description="CSS selector for targeted content extraction (not yet implemented)"
    )
    
    @field_validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @field_validator('device')
    def normalize_device(cls, v):
        """Standardize device naming."""
        device_mapping = {
            'desktop': 'Desktop Chrome',
            'mobile': 'iPhone 12',
            'tablet': 'iPad Pro'
        }
        return device_mapping.get(v.lower(), v)
    
    @field_validator('output_type')
    def normalize_output_types(cls, v):
        """Handle any format of output type specification."""
        try:
            # Convert any input to a string first for consistency
            input_str = str(v)
            
            # Remove all quotes (both single and double)
            cleaned = input_str.replace('"', '').replace("'", '')
            
            # Split by comma and clean up
            if ',' in cleaned:
                # Multiple types specified
                types = [t.strip().lower() for t in cleaned.split(',')]
                valid_types = []
                for t in types:
                    if t:  # Skip empty strings
                        try:
                            valid_types.append(OutputType(t))
                        except ValueError:
                            logger.warning(f"Invalid output type: {t}")
                
                if valid_types:
                    return valid_types
            else:
                # Single type
                try:
                    single_type = OutputType(cleaned.lower())
                    return single_type
                except ValueError:
                    logger.warning(f"Invalid output type: {cleaned}")
            
            # Default to TEXT if parsing failed
            logger.warning(f"Using default TEXT output type")
            return OutputType.TEXT
            
        except Exception as e:
            logger.error(f"Error normalizing output_type {repr(v)}: {str(e)}")
            # Default to TEXT if there's an error
            logger.warning(f"Defaulting to TEXT output_type due to validation error")
            return OutputType.TEXT
    
    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True

class ScrapperTool(BaseTool):
    """
    A tool that scrapes websites and extracts content in various formats.
    Supports multiple output types that can be combined by providing a comma-separated list:
    - html: Raw HTML content
    - cleaned_html: Cleaned HTML content
    - metadata: Page metadata (title, description, etc.)
    - text: Plain text content
    - links: Links found on the page
    - full: All of the above combined
    """
    name: str = "Web Scraper Tool"
    description: str = """
    A tool that scrapes websites and extracts content in various formats.
    Supports multiple output types that can be combined by providing a comma-separated list:
    - html: Raw HTML content
    - cleaned_html: Cleaned HTML content
    - metadata: Page metadata (title, description, etc.)
    - text: Plain text content
    - links: Links found on the page
    - full: All of the above combined
    
    Example combinations:
    - "metadata,links" - Get both metadata and links in one response
    - "text,metadata" - Get both text content and metadata
    - "links,html" - Get both links and raw HTML
    
    Use this tool to extract information from websites with flexible output format options.
    """
    args_schema: Type[BaseModel] = ScrapperToolSchema
    
    # Device presets for common types
    DEVICE_PRESETS: ClassVar[Dict[str, str]] = {
        'desktop': 'Desktop Chrome',
        'mobile': 'iPhone 12',
        'tablet': 'iPad Pro'
    }
    
    def _run(self, url: str, user_id: int, output_type: str = "text", 
            cache: bool = True, stealth: bool = True, timeout: int = 60000,
            device: str = "desktop", wait_until: str = "domcontentloaded",
            css_selector: Optional[str] = None, **kwargs) -> str:
        """
        Run the website scraping tool.
        
        Args:
            url: URL to scrape
            user_id: ID of the user initiating the scrape
            output_type: Type(s) of output. Can be a single value or a comma-separated list of types
                         (html, cleaned_html, metadata, text, links, or full)
            cache: Whether to use cached results
            stealth: Whether to use stealth mode
            timeout: Timeout in milliseconds
            device: Device to emulate
            wait_until: When to consider navigation successful
            css_selector: CSS selector for targeted content (not yet implemented)
            
        Returns:
            JSON string with the scraped content in the requested format(s)
        """
        try:
            # Log the raw output_type parameter for debugging
            
            # Normalize device name
            device = self.DEVICE_PRESETS.get(device.lower(), device)
            
            # Process output types - our validator should have already converted this to
            # either a single OutputType enum or a list of OutputType enums
            if isinstance(output_type, list):
                output_types = output_type
            else:
                output_types = [output_type]
                
            # Log the processed output types
            logger.info(f"Scraping URL: {url} with output_types: {output_types}")
            
            # Check if FULL is included - it already contains everything
            if OutputType.FULL in output_types:
                # If FULL is requested, we can ignore other types as it contains everything
                output_types = [OutputType.FULL]
            
            # Get domain for logging
            domain = urlparse(url).netloc
            
            # Initialize result container
            result = {
                "success": True,
                "url": url,
                "domain": domain
            }
            
            # Get content data (needed for most output types except LINKS)
            need_content = any(ot != OutputType.LINKS for ot in output_types)
            need_links = OutputType.LINKS in output_types or OutputType.FULL in output_types
            
            content_data = None
            links_data = None
            
            # Fetch content if needed
            if need_content:
                content_data = scrape_url(
                    url=url,
                    cache=cache,
                    stealth=stealth,
                    timeout=timeout,
                    device=device,
                    wait_until=wait_until
                )
                
                if not content_data:
                    return json.dumps({
                        "success": False,
                        "error": "Failed to retrieve content",
                        "url": url
                    })
            
            # Fetch links if needed
            if need_links:
                links_data = get_url_links(
                    url=url,
                    cache=cache,
                    stealth=stealth,
                    timeout=timeout,
                    device=device,
                    wait_until=wait_until,
                    text_len_threshold=40,  # Reasonable default
                    words_threshold=3       # Reasonable default
                )
                
                if not links_data and OutputType.LINKS in output_types:
                    # Only report failure if LINKS was explicitly requested
                    return json.dumps({
                        "success": False,
                        "error": "Failed to retrieve links",
                        "url": url
                    })
            
            # Process each requested output type
            for output_type_enum in output_types:
                if output_type_enum == OutputType.HTML and content_data:
                    result["html"] = content_data.get("fullContent", content_data.get("content", ""))
                
                elif output_type_enum == OutputType.CLEANED_HTML and content_data:
                    result["cleaned_html"] = content_data.get("content", "")
                
                elif output_type_enum == OutputType.TEXT and content_data:
                    text_content = content_data.get("textContent", "")
                    if not text_content:
                        # Try extracting text from HTML as fallback
                        from bs4 import BeautifulSoup
                        html_content = content_data.get("content", "")
                        if html_content:
                            soup = BeautifulSoup(html_content, 'html.parser')
                            text_content = soup.get_text(separator='\n', strip=True)
                    result["text"] = text_content
                
                elif output_type_enum == OutputType.METADATA and content_data:
                    result["title"] = content_data.get("title", "")
                    result["excerpt"] = content_data.get("excerpt", "")
                    result["length"] = content_data.get("length", 0)
                    result["meta"] = content_data.get("meta", {})
                
                elif output_type_enum == OutputType.LINKS and links_data:
                    result["links"] = links_data.get("links", [])
                    result["links_count"] = len(links_data.get("links", []))
                
                elif output_type_enum == OutputType.FULL:
                    # FULL output combines all types
                    if content_data:
                        result["html"] = content_data.get("fullContent", content_data.get("content", ""))
                        result["cleaned_html"] = content_data.get("content", "")
                        result["text"] = content_data.get("textContent", "")
                        result["title"] = content_data.get("title", "")
                        result["excerpt"] = content_data.get("excerpt", "")
                        result["length"] = content_data.get("length", 0)
                        result["meta"] = content_data.get("meta", {})
                    
                    if links_data:
                        result["links"] = links_data.get("links", [])
                        result["links_count"] = len(links_data.get("links", []))
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in ScrapperTool: {str(e)}", exc_info=True)
            error_response = {
                "success": False,
                "error": str(e),
                "url": url
            }
            return json.dumps(error_response, indent=2)
    
    # These methods are kept for backward compatibility with any code still 
    # calling them directly, but they're no longer used by the _run method
    def _format_html_output(self, data: Dict[str, Any]) -> str:
        """Format HTML output."""
        if data.get("fullContent"):
            # If full content was requested and available
            html_content = data["fullContent"]
        else:
            # Otherwise return the default content
            html_content = data.get("content", "")
            
        result = {
            "success": True,
            "url": data.get("url", ""),
            "html": html_content
        }
        return json.dumps(result, indent=2)
    
    def _format_cleaned_html_output(self, data: Dict[str, Any]) -> str:
        """Format cleaned HTML output."""
        cleaned_html = data.get("content", "")
        result = {
            "success": True,
            "url": data.get("url", ""),
            "cleaned_html": cleaned_html
        }
        return json.dumps(result, indent=2)
    
    def _format_text_output(self, data: Dict[str, Any]) -> str:
        """Format text output."""
        text_content = data.get("textContent", "")
        if not text_content:
            # Try extracting text from HTML as fallback
            from bs4 import BeautifulSoup
            html_content = data.get("content", "")
            if html_content:
                soup = BeautifulSoup(html_content, 'html.parser')
                text_content = soup.get_text(separator='\n', strip=True)
        
        result = {
            "success": True,
            "url": data.get("url", ""),
            "text": text_content
        }
        return json.dumps(result, indent=2)
    
    def _format_metadata_output(self, data: Dict[str, Any]) -> str:
        """Format metadata output."""
        metadata = {
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "domain": data.get("domain", ""),
            "excerpt": data.get("excerpt", ""),
            "length": data.get("length", 0),
            "meta": data.get("meta", {})
        }
        return json.dumps(metadata, indent=2)
    
    def _format_links_output(self, data: Dict[str, Any]) -> str:
        """Format links output."""
        result = {
            "url": data.get("url", ""),
            "domain": data.get("domain", ""),
            "title": data.get("title", ""),
            "links_count": len(data.get("links", [])),
            "links": data.get("links", [])
        }
        return json.dumps(result, indent=2)
    
    def _format_full_output(self, content_data: Dict[str, Any], links_data: Optional[Dict[str, Any]]) -> str:
        """Format full output with all content types."""
        # Start with basic info
        result = {
            "url": content_data.get("url", ""),
            "domain": content_data.get("domain", ""),
            "title": content_data.get("title", ""),
            "excerpt": content_data.get("excerpt", ""),
            "html": content_data.get("fullContent", content_data.get("content", "")),
            "cleaned_html": content_data.get("content", ""),
            "text": content_data.get("textContent", ""),
            "meta": content_data.get("meta", {}),
        }
        
        # Add links if available
        if links_data:
            result["links"] = links_data.get("links", [])
            result["links_count"] = len(links_data.get("links", []))
        
        return json.dumps(result, indent=2) 