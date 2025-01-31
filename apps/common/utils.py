import requests
import mimetypes
import urllib.parse
import re
from django.core.cache import cache
import logging
import tiktoken
from django.conf import settings
from langchain_community.chat_models import ChatOpenAI
from langchain_community.chat_models import ChatLiteLLM
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
import openai
from langchain.schema import HumanMessage
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import textwrap
from langchain_openai import ChatOpenAI
from crewai.llm import LLM

logger = logging.getLogger(__name__)

# Initialize markdown-it instance at module level for reuse
md = MarkdownIt('commonmark', {'html': True})

class TokenCounterCallback(BaseCallbackHandler):
    def __init__(self, tokenizer):
        self.llm = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.tokenizer = tokenizer

    def on_llm_start(self, serialized, prompts, **kwargs):
        for prompt in prompts:
            self.input_tokens += len(self.tokenizer.encode(prompt, disallowed_special=()))

    def on_llm_end(self, response, **kwargs):
        for generation in response.generations:
            for result in generation:
                self.output_tokens += len(self.tokenizer.encode(result.text, disallowed_special=()))

class ExtendedChatOpenAI(ChatOpenAI):
    """Extended ChatOpenAI with CrewAI required methods"""
    
    def supports_stop_words(self) -> bool:
        """Whether the LLM supports stop words"""
        return False

def get_models():
    """
    Fetches available models from the API with improved error handling and logging
    """
    try:
        # Check if we have cached models
        cached_models = cache.get('available_models')
        if cached_models:
            return cached_models

        # Construct URL and headers
        url = f'{settings.API_BASE_URL}/models'
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {settings.LITELLM_MASTER_KEY}'
        }
        
        # Log the request attempt
        logger.debug(f"Fetching models from {url}")
        
        # Make the request
        response = requests.get(url, headers=headers, timeout=10)
        
        # Log the response status
        logger.debug(f"Models API response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                logger.debug(f"Raw API response: {data}")  # Add this line to see full response

                if 'data' in data and isinstance(data['data'], list):
                    # Sort the models by ID
                    models = sorted([item['id'] for item in data['data']])
                    
                    # Cache the results for 5 minutes
                    cache.set('available_models', models, 300)
                    
                    logger.debug(f"Successfully fetched {len(models)} models")
                    return models
                else:
                    logger.error(f"Unexpected API response structure: {data}")
                    return []
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                return []
        else:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            return []
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in get_models: {str(e)}")
        return []

def get_llm(model_name: str, temperature: float = 0.7, streaming: bool = False):
    """Get LLM instance through LiteLLM proxy"""
    try:
        logger.debug(f"Initializing LLM with base URL: {settings.API_BASE_URL}")
        
        # Initialize ChatOpenAI with proxy settings
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
            base_url=settings.API_BASE_URL,
            api_key=settings.LITELLM_MASTER_KEY,
        )
        
        tokenizer = tiktoken.get_encoding("cl100k_base")
        token_counter = TokenCounterCallback(tokenizer)
        
        logger.debug(f"LLM initialized with model: {model_name}")
        return llm, token_counter
        
    except Exception as e:
        logger.error(f"Error initializing LLM: {str(e)}")
        logger.error(f"LLM configuration: base_url={settings.API_BASE_URL}, model={model_name}")
        raise

def is_pdf_url(url: str) -> bool:
    """Determine if the given URL points to a PDF document."""
    try:
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.path.endswith('.pdf'):
            return True
        response = requests.head(url, allow_redirects=True, timeout=5)
        content_type = response.headers.get('Content-Type')
        if content_type and content_type.startswith('application/pdf'):
            return True
        mime_type, _ = mimetypes.guess_type(url)
        if mime_type and mime_type.startswith('application/pdf'):
            return True
        response = requests.get(url, stream=True, timeout=5)
        return response.raw.read(1024).startswith(b'%PDF-')
    except requests.exceptions.RequestException:
        return False

def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url

def is_stock_symbol(query):
    url = f'https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={query}&apikey={settings.ALPHA_VANTAGE_API_KEY}'
    r=requests.get(url)
    data = r.json()
    print(data)
    if 'bestMatches' in data and len(data['bestMatches']) > 0:
        return True
    else:
        return False

def tokenize(text: str, tokenizer = "cl100k_base") -> int:
    """ Helper function to tokenize text and return token count """
    return len(tokenizer.encode(text, disallowed_special=()))

def extract_top_level_domain(url):
  """Extracts only the top-level domain (TLD) from a URL, handling various cases.

  Args:
    url: The URL to extract the TLD from.

  Returns:
    The top-level domain (TLD) as a string (without protocol or subdomains), 
    or None if the TLD cannot be determined or if None is passed in.
  """
  if url is None:
    return None  # Handle None input explicitly

  try:
    # Remove protocol (http://, https://)
    url = url.split("//")[-1]  
    # Remove trailing slash
    url = url.rstrip("/")
    # Split into parts and extract TLD using the previous logic
    url_parts = url.split(".")
    if len(url_parts) > 1 and url_parts[-1] in {"com", "org", "net", "edu", "gov", "mil"}:
      return url_parts[-2]  # Return TLD (e.g., sld.com, sld.org)
    elif len(url_parts) > 2 and url_parts[-3] in {"co", "ac"}:
      return ".".join(url_parts[-2:])  # Handle "sld.co.uk", etc.
    else:
      return url_parts[-1]  # Default to last part 
  except IndexError:
    return None 

def normalize_url(url):
    """Normalize a single URL"""
    url = url.lower()
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.port == 80 and parsed_url.scheme == 'http':
        parsed_url = parsed_url._replace(netloc=parsed_url.netloc.split(':')[0])
    url = urllib.parse.urlunparse(parsed_url)
    url = url.rstrip('/')
    url = urllib.parse.urldefrag(url)[0]
    url = urllib.parse.unquote(url)
    return url

def compare_urls(url1, url2):
    """Compare two URLs after normalizing them"""
    url1 = normalize_url(url1)
    url2 = normalize_url(url2)
    return url1 == url2

def format_message(content):
    if not content:
        return ''
    
    # Process ANSI color codes
    color_map = {
        '\x1b[1m': '<strong>',
        '\x1b[0m': '</strong>',
        '\x1b[93m': '<span class="text-warning">',  # Yellow
        '\x1b[92m': '<span class="text-success">',  # Green
        '\x1b[95m': '<span class="text-info">',     # Light Blue (for magenta)
        '\x1b[91m': '<span class="text-danger">',   # Red
        '\x1b[94m': '<span class="text-primary">',  # Blue
    }

    # Replace color codes with Bootstrap classes
    for code, html in color_map.items():
        content = content.replace(code, html)

    # Remove any remaining ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    content = ansi_escape.sub('', content)

    try:
        # Convert Markdown to HTML using markdown-it
        html_content = md.render(content)

        # Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Add Bootstrap classes to elements
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            tag['class'] = tag.get('class', []) + ['mt-3', 'mb-2']
        
        for tag in soup.find_all('p'):
            tag['class'] = tag.get('class', []) + ['mb-2']
        
        for tag in soup.find_all('ul', 'ol'):
            tag['class'] = tag.get('class', []) + ['pl-4']
        
        for tag in soup.find_all('code'):
            tag['class'] = tag.get('class', []) + ['bg-light', 'p-1', 'rounded']

        # Convert back to string
        formatted_content = str(soup)

        # Ensure all spans are closed
        open_spans = formatted_content.count('<span')
        close_spans = formatted_content.count('</span>')
        if open_spans > close_spans:
            formatted_content += '</span>' * (open_spans - close_spans)

        return formatted_content
    except Exception as e:
        logger.error(f"Error formatting message: {str(e)}")
        return content  # Return original content if formatting fails

class DateProcessor:
    @staticmethod
    def process_relative_date(date_str: str) -> str:
        """
        Convert relative dates to YYYY-MM-DD format
        Supports:
        - NdaysAgo (e.g., 7daysAgo)
        - NmonthsAgo (e.g., 3monthsAgo)
        - today
        - yesterday
        - YYYY-MM-DD format
        """
        if date_str == 'today':
            return datetime.now().strftime('%Y-%m-%d')
        
        if date_str == 'yesterday':
            return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
        # Check for NmonthsAgo format
        months_match = re.match(r'^(\d+)monthsAgo$', date_str)
        if months_match:
            months = int(months_match.group(1))
            return (datetime.now() - relativedelta(months=months)).strftime('%Y-%m-%d')
            
        # Check for NdaysAgo format
        days_match = re.match(r'^(\d+)daysAgo$', date_str)
        if days_match:
            days = int(days_match.group(1))
            return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
        # Assume YYYY-MM-DD format
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            raise ValueError(
                "Invalid date format. Use either:\n"
                "- YYYY-MM-DD (e.g., 2024-03-15)\n"
                "- 'today' or 'yesterday'\n"
                "- 'NdaysAgo' where N is a positive number (e.g., 7daysAgo)\n"
                "- 'NmonthsAgo' where N is a positive number (e.g., 3monthsAgo)"
            )

def create_box(title: str, content: str) -> str:
    """Create a boxed debug message with wrapped content using Unicode box characters."""
    # Box drawing characters
    TOP_LEFT = "┌"
    TOP_RIGHT = "┐"
    BOTTOM_LEFT = "└"
    BOTTOM_RIGHT = "┘"
    HORIZONTAL = "─"
    VERTICAL = "│"
    
    # Wrap content to 80 chars
    wrapped_content = textwrap.fill(str(content), width=80)
    width = max(max(len(line) for line in wrapped_content.split('\n')), len(title)) + 4
    
    # Create box components
    top = f"{TOP_LEFT}{HORIZONTAL * (width-2)}{TOP_RIGHT}"
    title_line = f"{VERTICAL} {title.center(width-4)} {VERTICAL}"
    separator = f"{HORIZONTAL * width}"
    content_lines = [f"{VERTICAL} {line:<{width-4}} {VERTICAL}" for line in wrapped_content.split('\n')]
    bottom = f"{BOTTOM_LEFT}{HORIZONTAL * (width-2)}{BOTTOM_RIGHT}"
    
    return f"\n{top}\n{title_line}\n{separator}\n{chr(10).join(content_lines)}\n{bottom}\n"

