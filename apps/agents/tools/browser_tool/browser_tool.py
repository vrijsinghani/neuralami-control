import json
import os
from typing import Any, Type, Set, Dict
import logging
import re
from tenacity import retry, stop_after_attempt, wait_exponential

import requests
from pydantic import BaseModel, Field
import html2text
from crewai_tools import BaseTool
from urllib.parse import urljoin, urlparse
import dotenv
from bs4 import BeautifulSoup
import trafilatura
from readability.readability import Document

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class BrowserToolSchema(BaseModel):
  """Input for BrowserTool."""
  website: str = Field(..., title="Website", description="Full URL of the website to scrape (e.g., https://google.com)")
  output_type: str = Field(
      default="text",
      title="Output Type",
      description="Type of output desired: 'text' for cleaned content or 'raw' for HTML"
  )

class BrowserTool(BaseTool):
  name: str = "Scrape website content"
  description: str = "A tool that can be used to scrape website content. Pass a string with only the full URL, no need for a final slash `/`. output_type can be 'text' for cleaned content or 'raw' for HTML."
  output_type: str = "text"
  tags: Set[str] = {"browser", "scrape", "website", "content"}
  args_schema: Type[BaseModel] = BrowserToolSchema
  api_key: str = Field(default=os.environ.get('BROWSERLESS_API_KEY'))
  base_url: str = Field(default="https://browserless.rijsinghani.us/scrape")

  def __init__(self, **data):
      super().__init__(**data)
      if not self.api_key:
          logger.error("BROWSERLESS_API_KEY is not set in the environment variables.")

  def _run(
      self,
      website: str,
      output_type: str = "text",
      **kwargs: Any,
  ) -> Any:
      """Scrape website content."""
      website = self.normalize_url(website)
      logger.info(f"Scraping website: {website} with output type: {output_type}")
      content = self.get_content(website, output_type)
      if output_type == "raw":
          return content  # Return raw HTML directly
      return content  # Return processed text directly

  def normalize_url(self, url: str) -> str:
      """Normalize the URL by adding the protocol if missing."""
      if not re.match(r'^\w+://', url):
          return f"https://{url}"
      return url

  def clean_content(self, content: str) -> str:
      """Clean and structure extracted content"""
      if not content:
          return ""
          
      # Remove excessive whitespace
      content = re.sub(r'\s+', ' ', content)
      
      # Remove common boilerplate phrases
      boilerplate = [
          'cookie policy',
          'accept cookies',
          'privacy policy',
          'terms of service',
          'subscribe to our newsletter',
          'sign up for our newsletter',
          'all rights reserved',
      ]
      for phrase in boilerplate:
          content = re.sub(rf'(?i){phrase}.*?[\.\n]', '', content)
      
      # Remove email addresses and phone numbers
    #   content = re.sub(r'\S+@\S+', '[EMAIL]', content)
    #   content = re.sub(r'\+?\d{1,3}[-.\s]?$?\d{3}$?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', content)
      
      return content.strip()

  def detect_content_type(self, url: str, html_content: str) -> str:
      """Detect type of content for specialized handling"""
      patterns = {
          'article': r'article|post|blog',
          'product': r'product|item|price',
          'documentation': r'docs|documentation|api|reference',
      }
      
      for content_type, pattern in patterns.items():
          if re.search(pattern, url, re.I) or re.search(pattern, html_content, re.I):
              return content_type
      return 'general'

  def extract_content(self, url: str, html_content: str) -> dict:
      """Multi-strategy content extraction"""
      content = {
          'title': '',
          'text': '',
          'metadata': {}
      }
      
      try:
          # Strategy 1: Trafilatura
          trafilatura_content = trafilatura.extract(html_content, include_comments=False, 
                                                  include_tables=True, 
                                                  include_links=False)
          
          # Strategy 2: Readability
          doc = Document(html_content)
          readable_article = doc.summary()
          doc_title = doc.title()
          
          # Strategy 3: BeautifulSoup fallback
          soup = BeautifulSoup(html_content, 'lxml')
          
          # Combine results with priority
          if trafilatura_content:
              content['text'] = trafilatura_content
          elif readable_article:
              soup_readable = BeautifulSoup(readable_article, 'lxml')
              content['text'] = soup_readable.get_text(separator=' ', strip=True)
          else:
              content['text'] = soup.get_text(separator=' ', strip=True)
              
          # Extract title
          content['title'] = doc_title or soup.title.string if soup.title else ''
          
          # Extract basic metadata
          meta_tags = soup.find_all('meta')
          content['metadata'] = {
              'description': next((tag.get('content', '') for tag in meta_tags if tag.get('name', '').lower() == 'description'), ''),
              'keywords': next((tag.get('content', '').split(',') for tag in meta_tags if tag.get('name', '').lower() == 'keywords'), []),
              'author': next((tag.get('content', '') for tag in meta_tags if tag.get('name', '').lower() == 'author'), '')
          }
          
      except Exception as e:
          logger.error(f"Error in content extraction: {str(e)}")
          # Fallback to basic HTML extraction
          content['text'] = html2text.html2text(html_content)
              
      return content

  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=4, max=10),
      reraise=True
  )
  def get_content(self, url: str, output_type: str = "text") -> str:
      """Scrape website content with retry mechanism."""
      # Check if URL is an image or other non-HTML content
      parsed_url = urlparse(url)
      path = parsed_url.path.lower()
      if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.pdf']):
          logger.info(f"Skipping content extraction for non-HTML file: {url}")
          return f"Non-HTML content: {url}"

      payload = {
          "url": url,
          "elements": [{"selector": "html"}]  # Changed from 'body' to 'html' to get full document
      }
      headers = {'cache-control': 'no-cache', 'content-type': 'application/json'}
      
      response = None
      try:
          #logger.info(f"Attempting to fetch content from {url}")
          response = requests.post(
              f"{self.base_url}?token={self.api_key}", 
              headers=headers, 
              json=payload,
              timeout=30
          )
          response.raise_for_status()
          
          try:
              data = response.json()
          except ValueError as e:
              logger.error(f"Failed to parse JSON response for {url}: {str(e)}")
              logger.error(f"Response content: {response.text[:500]}...")  # Log first 500 chars
              return ""

          if not data.get('data') or not data['data'][0].get('results'):
              logger.error(f"Unexpected response structure for {url}")
              logger.error(f"Response data: {json.dumps(data)[:500]}...")  # Log first 500 chars
              return ""

          html_content = data['data'][0]['results'][0]['html']
          if not html_content:
              logger.warning(f"Empty HTML content received for {url}")
              return ""

          # Add doctype if missing to ensure proper parsing
          if not html_content.lower().startswith('<!doctype'):
              html_content = '<!DOCTYPE html>\n' + html_content

          # Return raw HTML if requested
          if output_type.lower() == "raw":
              return html_content

          # Otherwise process the content as before
          try:
              content_type = self.detect_content_type(url, html_content)
              extracted_content = self.extract_content(url, html_content)
          except Exception as e:
              logger.error(f"Error processing content for {url}: {str(e)}")
              return html_content  # Fallback to raw HTML on processing error

          # Format the final output
          result = f"Title: {extracted_content['title']}\n\n"
          result += f"Content Type: {content_type}\n\n"
          result += extracted_content['text']

          # Add metadata if available
          if extracted_content['metadata'].get('description'):
              result += f"\n\nDescription: {extracted_content['metadata']['description']}"
          if extracted_content['metadata'].get('author'):
              result += f"\nAuthor: {extracted_content['metadata']['author']}"
          if extracted_content['metadata'].get('keywords'):
              result += f"\nKeywords: {', '.join(extracted_content['metadata']['keywords'])}"
          
          logger.info(f"Successfully extracted content from {url}")
          return result

      except requests.exceptions.Timeout as e:
          logger.error(f"Timeout while fetching content from {url}: {str(e)}")
          raise  # Let the retry decorator handle timeouts
          
      except requests.exceptions.RequestException as e:
          logger.error(f"Failed to fetch content for {url}: {str(e)}")
          if response is not None:
              logger.error(f"Response status code: {response.status_code}")
              logger.error(f"Response content: {response.text[:500]}...")  # Log first 500 chars
          return ""
          
      except Exception as e:
          logger.error(f"Unexpected error while processing {url}: {str(e)}")
          return ""

  def get_links(self, url: str) -> Set[str]:
      """Extract links from the webpage."""
      payload = {
          "url": url,
          "elements": [
              {"selector": "a"}
          ]
      }
      headers = {'Cache-Control': 'no-cache', 'Content-Type': 'application/json'}
      try:
          response = requests.post(f"{self.base_url}?token={self.api_key}", 
                                headers=headers, 
                                json=payload,
                                timeout=30)
          response.raise_for_status()
          data = response.json()
          links = set()
          base_domain = urlparse(url).netloc
          for element in data['data'][0]['results']:
              for attr in element['attributes']:
                  if attr['name'] == 'href':
                      full_url = urljoin(url, attr['value'])
                      if urlparse(full_url).netloc == base_domain:
                          links.add(full_url)
          return links
      except requests.exceptions.RequestException as e:
          logger.error(f"Failed to fetch links for {url}: {str(e)}")
          logger.error(f"Response status code: {getattr(response, 'status_code', 'N/A')}")
          logger.error(f"Response content: {getattr(response, 'text', 'N/A')}")
          return set()

  def check_url_status(self, url: str) -> Dict[str, Any]:
      """Check if a URL is accessible and return its status."""
      try:
          response = self._run(url, output_type="status")
          return {
              'status_code': response.get('status_code', 500),
              'error': None
          }
      except Exception as e:
          return {
              'status_code': 500,
              'error': str(e)
          }