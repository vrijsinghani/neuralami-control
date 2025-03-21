from .utils import is_pdf_url, is_youtube, is_stock_symbol
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.agents.utils.scrape_url import scrape_url
from langchain_community.document_loaders import YoutubeLoader, PyMuPDFLoader
import logging
from sec_edgar_downloader import Downloader
import os
from bs4 import BeautifulSoup
from django.conf import settings
import json

logger = logging.getLogger(__name__)

class ContentLoader:
    def __init__(self):
        self.crawl_tool = CrawlWebsiteTool()

    def load_content(self, query: str, user_id: int = None, crawl_website: bool = False, max_pages: int = 10) -> str:
        """Load content from various sources"""
        logging.info(f"Loading content from website: {query} (crawl_website={crawl_website}, max_pages={max_pages})")
        
        # Check if it's a URL
        if query.startswith('http://') or query.startswith('https://'):
            if crawl_website and max_pages > 1:
                # Use CrawlWebsiteTool to get content from multiple pages
                result_json = self.crawl_tool.run(
                    website_url=query,
                    user_id=user_id,
                    max_pages=max_pages,
                    output_type="markdown"
                )
                
                # Parse JSON result
                try:
                    result = json.loads(result_json)
                except (json.JSONDecodeError, TypeError):
                    # If it's not valid JSON, use it as a string
                    result = result_json
                
                # Handle both dictionary and string responses
                if isinstance(result, dict):
                    if result.get('status') == 'success':
                        results = result.get('results', [])
                        if results:
                            return "\n\n".join(page.get('content', '') for page in results)
                        else:
                            return "Error: No content found in crawled pages"
                    else:
                        return f"Error crawling website: {result.get('message', 'Unknown error')}"
                else:
                    # If result is a string, it's likely an error message
                    return f"Error crawling website: {result}"
            else:
                # Use scrape_url to get content from the URL (handles regular URLs, PDFs, and YouTube)
                scrape_result = scrape_url(query)
                
                if scrape_result is None:
                    return f"Error: Failed to scrape content from {query}"
                
                # Extract content based on content type
                content_type = scrape_result.get('meta', {}).get('contentType', 'html')
                
                if content_type == 'youtube':
                    # For YouTube, return the formatted content
                    return scrape_result.get('content', '')
                elif content_type == 'pdf':
                    # For PDF, return the text content
                    return scrape_result.get('textContent', '')
                else:
                    # For regular webpages, return the markdown content
                    return scrape_result.get('textContent', '')
        elif is_stock_symbol(query):
                logger.info(f"Loading content from SEC EDGAR: {query}")
                return self._load_from_sec(query)
        else:
            logger.info("Loading as text")
            return query

    def _load_from_sec(self, query: str) -> str:
        """ Load and return content from SEC EDGAR """
        # Provide a company name and email address to comply with SEC EDGAR's fair access policy
        company_name = settings.COMPANY_NAME
        email_address = settings.EMAIL_ADDRESS

        # Create a Downloader instance with the specified download folder
        download_folder = settings.DOWNLOAD_FOLDER + "/sec-edgar-files"
        
        dl = Downloader(company_name, email_address, download_folder)

        num_filings_downloaded = dl.get("10-K", query, limit=1, download_details=True)
        logging.info(f"Downloaded {num_filings_downloaded} 10-K filing(s) for {query}.")

        print(f"Downloaded {num_filings_downloaded} 10-K filing(s) for {query}.")

        # Access the downloaded HTML filing
        if num_filings_downloaded > 0:
            logging.info("getting filings dir")
            filings_dir = os.path.join(download_folder, "sec-edgar-filings", query, "10-K")
            filing_subdirs = os.listdir(filings_dir)
            # latest_filing_subdir = sorted(filing_subdirs)[-1]
            # latest_filing_path = os.path.join(filings_dir, latest_filing_subdir, "primary-document.html")
            logging.info("getting latest_filings_subdir")
            latest_filing_subdir = sorted(filing_subdirs)[-1]
            # Convert set to string if necessary
            if not isinstance(latest_filing_subdir, str):
                latest_filing_subdir = str(latest_filing_subdir)
            logging.info("getting latest_filing_path")
            latest_filing_path = os.path.join(filings_dir, latest_filing_subdir, "primary-document.html")

            
            
            with open(latest_filing_path, "r") as f:
                html_content = f.read()
            
            # Parse the HTML content using BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract the text content
            text_content = soup.get_text()
            
            return text_content
