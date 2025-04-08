"""
Base adapter interface for web scraping services.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union


class ScraperAdapter(ABC):
    """Base adapter interface for web scraping services."""
    
    @abstractmethod
    def scrape(self, 
               url: str, 
               formats: List[str], 
               timeout: int = 30000,
               wait_for: Optional[int] = None,
               css_selector: Optional[str] = None,
               headers: Optional[Dict[str, str]] = None,
               mobile: bool = False,
               stealth: bool = False,
               **kwargs) -> Dict[str, Any]:
        """
        Scrape a URL and return the content in the requested formats.
        
        Args:
            url: The URL to scrape
            formats: List of formats to return (text, html, links, metadata, full)
            timeout: Timeout in milliseconds
            wait_for: Wait for element or time in milliseconds
            css_selector: CSS selector to extract content from
            headers: Custom headers to send with the request
            mobile: Whether to use mobile user agent
            stealth: Whether to use stealth mode
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dictionary with the requested formats as keys and their content as values
        """
        pass
    
    @abstractmethod
    def get_supported_formats(self) -> List[str]:
        """
        Get the list of formats supported by this adapter.
        
        Returns:
            List of supported format names
        """
        pass
    
    @abstractmethod
    def map_formats(self, formats: Union[str, List[str]]) -> List[str]:
        """
        Map internal format names to provider-specific format names.
        
        Args:
            formats: List of internal format names or comma-separated string
            
        Returns:
            List of provider-specific format names
        """
        pass
