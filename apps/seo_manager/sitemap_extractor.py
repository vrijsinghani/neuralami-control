import os
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from datetime import datetime
from apps.common.tools.user_activity_tool import user_activity_tool
import logging
import io

logger = logging.getLogger(__name__)

def extract_sitemap_and_meta_tags(client, user):
    """
    Extract sitemap and meta tags from a client's website and save to cloud storage.
    
    Args:
        client: The client instance
        user: The user instance
        
    Returns:
        str: The relative path to the saved file
    """
    try:
        base_url = client.website_url.rstrip('/')  # Remove trailing slash if present
        fqdn = urlparse(base_url).netloc
        date_str = datetime.now().strftime("%y-%m-%d")
        file_name = f"{fqdn}-{date_str}.csv"
        relative_path = os.path.join(str(user.id), 'meta-tags', file_name)

        visited_urls = set()
        urls_to_visit = set()

        def process_sitemap(sitemap_url):
            logger.debug(f"Processing sitemap: {sitemap_url}")
            try:
                response = requests.get(sitemap_url, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    for loc in soup.find_all('loc'):
                        url = loc.text.strip()
                        if url.endswith('.xml'):
                            process_sitemap(url)
                        else:
                            urls_to_visit.add(url)
            except requests.RequestException as e:
                logger.error(f"Error processing sitemap {sitemap_url}: {e}")

        # Step 1: Look for sitemaps
        sitemap_urls = [
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap",
        ]

        for sitemap_url in sitemap_urls:
            process_sitemap(sitemap_url)

        # If no sitemap found, start with the base URL
        if not urls_to_visit:
            urls_to_visit.add(base_url)

        # Create a CSV in memory
        output = io.StringIO()
        fieldnames = ['url', 'title', 'meta_description', 'meta_charset', 'viewport', 
                     'robots', 'canonical', 'og_title', 'og_description', 'og_image', 
                     'twitter_card', 'twitter_title', 'twitter_description', 
                     'twitter_image', 'author', 'language']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        while urls_to_visit:
            url = urls_to_visit.pop()

            if url in visited_urls:
                continue

            # Step 4: Exclude URLs with specific words, anchor links, and query strings
            if any(word in url for word in ['blog', 'product-id', 'search', 'page', 'wp-content']) or '#' in url or '?' in url:
                continue

            try:
                logger.debug(f"Visiting URL: {url}")
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
                logger.debug(f"Response: {response.status_code}")
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    # Step 3: Extract meta tags
                    meta_tags = {
                        'url': url,
                        'title': soup.title.string if soup.title else '',
                        'meta_description': soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={'name': 'description'}) else '',
                        'meta_charset': soup.find('meta', attrs={'charset': True})['charset'] if soup.find('meta', attrs={'charset': True}) else '',
                        'viewport': soup.find('meta', attrs={'name': 'viewport'})['content'] if soup.find('meta', attrs={'name': 'viewport'}) else '',
                        'robots': soup.find('meta', attrs={'name': 'robots'})['content'] if soup.find('meta', attrs={'name': 'robots'}) else '',
                        'canonical': soup.find('link', attrs={'rel': 'canonical'})['href'] if soup.find('link', attrs={'rel': 'canonical'}) else '',
                        'og_title': soup.find('meta', attrs={'property': 'og:title'})['content'] if soup.find('meta', attrs={'property': 'og:title'}) else '',
                        'og_description': soup.find('meta', attrs={'property': 'og:description'})['content'] if soup.find('meta', attrs={'property': 'og:description'}) else '',
                        'og_image': soup.find('meta', attrs={'property': 'og:image'})['content'] if soup.find('meta', attrs={'property': 'og:image'}) else '',
                        'twitter_card': soup.find('meta', attrs={'name': 'twitter:card'})['content'] if soup.find('meta', attrs={'name': 'twitter:card'}) else '',
                        'twitter_title': soup.find('meta', attrs={'name': 'twitter:title'})['content'] if soup.find('meta', attrs={'name': 'twitter:title'}) else '',
                        'twitter_description': soup.find('meta', attrs={'name': 'twitter:description'})['content'] if soup.find('meta', attrs={'name': 'twitter:description'}) else '',
                        'twitter_image': soup.find('meta', attrs={'name': 'twitter:image'})['content'] if soup.find('meta', attrs={'name': 'twitter:image'}) else '',
                        'author': soup.find('meta', attrs={'name': 'author'})['content'] if soup.find('meta', attrs={'name': 'author'}) else '',
                        'language': soup.find('html').get('lang', '') if soup.find('html') else '',
                    }

                    writer.writerow(meta_tags)

                    # Step 2: Extract internal links
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if '#' in href or '?' in href:
                            continue
                        full_url = urljoin(url, href)
                        full_url = full_url.split('#')[0]
                        if full_url.startswith(base_url) and full_url not in visited_urls and full_url not in urls_to_visit:
                            urls_to_visit.add(full_url)

                    visited_urls.add(url)

            except requests.RequestException as e:
                logger.error(f"Error processing URL {url}: {e}")

        # Save the CSV to cloud storage
        default_storage.save(relative_path, ContentFile(output.getvalue()))
        output.close()

        # Log the activity
        user_activity_tool.run(user, 'create', f"Created meta tags snapshot for client: {client.name}", 
                             client=client, details={'file_name': file_name})

        return relative_path

    except Exception as e:
        logger.error(f"Error in extract_sitemap_and_meta_tags: {str(e)}")
        raise

def extract_sitemap_and_meta_tags_from_url(url, user):
    """
    Extract sitemap and meta tags from a URL and save to cloud storage.
    
    Args:
        url: The URL to extract from
        user: The user instance
        
    Returns:
        str: The relative path to the saved file
    """
    try:
        base_url = url.rstrip('/')
        fqdn = urlparse(base_url).netloc
        date_str = datetime.now().strftime("%y-%m-%d")
        file_name = f"{fqdn}-{date_str}.csv"
        relative_path = os.path.join(str(user.id), 'meta-tags', file_name)

        visited_urls = set()
        urls_to_visit = set()

        def process_sitemap(sitemap_url):
            logger.debug(f"Processing sitemap: {sitemap_url}")
            try:
                response = requests.get(sitemap_url, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    for loc in soup.find_all('loc'):
                        url = loc.text.strip()
                        if url.endswith('.xml'):
                            process_sitemap(url)
                        else:
                            urls_to_visit.add(url)
            except requests.RequestException as e:
                logger.error(f"Error processing sitemap {sitemap_url}: {e}")

        # Step 1: Look for sitemaps
        sitemap_urls = [
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap",
        ]

        for sitemap_url in sitemap_urls:
            process_sitemap(sitemap_url)

        # If no sitemap found, start with the base URL
        if not urls_to_visit:
            urls_to_visit.add(base_url)

        # Create a CSV in memory
        output = io.StringIO()
        fieldnames = ['url', 'title', 'meta_description', 'meta_charset', 'viewport', 
                     'robots', 'canonical', 'og_title', 'og_description', 'og_image', 
                     'twitter_card', 'twitter_title', 'twitter_description', 
                     'twitter_image', 'author', 'language']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        while urls_to_visit:
            url = urls_to_visit.pop()

            if url in visited_urls:
                continue

            # Step 4: Exclude URLs with specific words, anchor links, and query strings
            if any(word in url for word in ['blog', 'product-id', 'search', 'page', 'wp-content']) or '#' in url or '?' in url:
                continue

            try:
                logger.debug(f"Visiting URL: {url}")
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
                logger.debug(f"Response: {response.status_code}")
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    # Step 3: Extract meta tags
                    meta_tags = {
                        'url': url,
                        'title': soup.title.string if soup.title else '',
                        'meta_description': soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={'name': 'description'}) else '',
                        'meta_charset': soup.find('meta', attrs={'charset': True})['charset'] if soup.find('meta', attrs={'charset': True}) else '',
                        'viewport': soup.find('meta', attrs={'name': 'viewport'})['content'] if soup.find('meta', attrs={'name': 'viewport'}) else '',
                        'robots': soup.find('meta', attrs={'name': 'robots'})['content'] if soup.find('meta', attrs={'name': 'robots'}) else '',
                        'canonical': soup.find('link', attrs={'rel': 'canonical'})['href'] if soup.find('link', attrs={'rel': 'canonical'}) else '',
                        'og_title': soup.find('meta', attrs={'property': 'og:title'})['content'] if soup.find('meta', attrs={'property': 'og:title'}) else '',
                        'og_description': soup.find('meta', attrs={'property': 'og:description'})['content'] if soup.find('meta', attrs={'property': 'og:description'}) else '',
                        'og_image': soup.find('meta', attrs={'property': 'og:image'})['content'] if soup.find('meta', attrs={'property': 'og:image'}) else '',
                        'twitter_card': soup.find('meta', attrs={'name': 'twitter:card'})['content'] if soup.find('meta', attrs={'name': 'twitter:card'}) else '',
                        'twitter_title': soup.find('meta', attrs={'name': 'twitter:title'})['content'] if soup.find('meta', attrs={'name': 'twitter:title'}) else '',
                        'twitter_description': soup.find('meta', attrs={'name': 'twitter:description'})['content'] if soup.find('meta', attrs={'name': 'twitter:description'}) else '',
                        'twitter_image': soup.find('meta', attrs={'name': 'twitter:image'})['content'] if soup.find('meta', attrs={'name': 'twitter:image'}) else '',
                        'author': soup.find('meta', attrs={'name': 'author'})['content'] if soup.find('meta', attrs={'name': 'author'}) else '',
                        'language': soup.find('html').get('lang', '') if soup.find('html') else '',
                    }

                    writer.writerow(meta_tags)

                    # Step 2: Extract internal links
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if '#' in href or '?' in href:
                            continue
                        full_url = urljoin(url, href)
                        full_url = full_url.split('#')[0]
                        if full_url.startswith(base_url) and full_url not in visited_urls and full_url not in urls_to_visit:
                            urls_to_visit.add(full_url)

                    visited_urls.add(url)

            except requests.RequestException as e:
                logger.error(f"Error processing URL {url}: {e}")

        # Save to cloud storage instead of local file
        default_storage.save(relative_path, ContentFile(output.getvalue()))
        output.close()

        # Log the activity without a client
        user_activity_tool.run(user, 'create', f"Created meta tags snapshot for URL: {url}", 
                             details={'file_name': file_name})

        return relative_path

    except Exception as e:
        logger.error(f"Error in extract_sitemap_and_meta_tags_from_url: {str(e)}")
        raise
