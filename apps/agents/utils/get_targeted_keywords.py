from bs4 import BeautifulSoup
from boilerpy3 import extractors
from rake_nltk import Rake
from collections import Counter
import re
from nltk.corpus import stopwords
import nltk
import logging

logger = logging.getLogger(__name__)

# Ensure NLTK data is downloaded
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# Extended list of web-specific stopwords to filter out
WEB_SPECIFIC_STOPWORDS = {
    # Common website terms
    'cookie', 'cookies', 'privacy', 'policy', 'terms', 'conditions',
    'accept', 'decline', 'website', 'site', 'click', 'homepage',
    
    # Navigation terms
    'menu', 'navigation', 'nav', 'sidebar', 'footer', 'header',
    'login', 'signin', 'signup', 'register', 'account',
    
    # UI elements
    'button', 'link', 'image', 'icon', 'logo', 'banner',
    'scroll', 'dropdown', 'popup', 'modal',
    
    # Generic web actions
    'click', 'submit', 'cancel', 'close', 'open', 'save', 'delete',
    'download', 'upload', 'share', 'like', 'follow',
    
    # Generic fillers
    'please', 'thank', 'thanks', 'welcome', 'hello', 'get', 'make',
    'read', 'learn', 'find', 'see', 'view', 'check',
    
    # Time-related
    'today', 'yesterday', 'tomorrow', 'week', 'month', 'year',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 
    'august', 'september', 'october', 'november', 'december'
}

def get_targeted_keywords(html_text, top_n=10):
    """
    Extracts keywords a webpage is targeting for SEO based on its HTML content.

    Args:
        html_text (str): The HTML content of the webpage to analyze.
        top_n (int): The number of top keywords to return (default is 10).

    Returns:
        list: A list of the top targeted keywords.
    """
    try:
        # Step 1: Extract the main content using boilerpy3
        extractor = extractors.ArticleExtractor()
        main_content = extractor.get_content(html_text)

        # Step 2: Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_text, 'html.parser')

        # Extract title
        title = soup.title.string if soup.title else ''

        # Extract meta description
        meta_desc = ''
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag and 'content' in meta_tag.attrs:
            meta_desc = meta_tag['content']

        # Extract H1 and H2 headers
        headers = [header.get_text(strip=True) for header in soup.find_all(['h1', 'h2'])]

        # Step 3: Keyword extraction
        # Initialize RAKE for main content keyword extraction
        rake = Rake()
        rake.extract_keywords_from_text(main_content)
        main_keywords = rake.get_ranked_phrases()[:10]  # Limit to top 10 phrases

        # Helper function to extract keywords from short text
        standard_stop_words = set(stopwords.words('english'))
        # Combine standard stopwords with our custom web-specific stopwords
        enhanced_stop_words = standard_stop_words.union(WEB_SPECIFIC_STOPWORDS)
        
        def extract_keywords(text):
            words = re.findall(r'\w+', text.lower())
            return [word for word in words if word not in enhanced_stop_words and len(word) > 2]

        # Extract keywords from title, meta description, and headers
        title_keywords = extract_keywords(title)
        meta_keywords = extract_keywords(meta_desc)
        header_keywords = []
        for header in headers:
            header_keywords.extend(extract_keywords(header))

        # Step 4: Combine and score keywords
        keyword_scores = Counter()

        # Assign weights to keywords based on their source
        for keyword in title_keywords:
            keyword_scores[keyword] += 3  # High importance for title
        for keyword in meta_keywords:
            keyword_scores[keyword] += 2  # Medium importance for meta description
        for keyword in header_keywords:
            keyword_scores[keyword] += 2  # Medium importance for headers
        for phrase in main_keywords:
            words = re.findall(r'\w+', phrase.lower())
            for word in words:
                if word not in enhanced_stop_words and len(word) > 2:
                    keyword_scores[word] += 1  # Lower importance for main content

        # Step 5: Get the top N keywords
        top_keywords = [keyword for keyword, _ in keyword_scores.most_common(top_n)]
        return top_keywords

    except Exception as e:
        logger.error(f"Error extracting keywords: {e}")
        return [] 