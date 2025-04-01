import os
import csv
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from core.storage import SecureFileStorage
from django.core.files.base import ContentFile
from datetime import datetime
from apps.common.tools.user_activity_tool import user_activity_tool
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool
import logging
import io

logger = logging.getLogger(__name__)

# Instantiate SecureFileStorage for meta tags
meta_tag_storage = SecureFileStorage(private=True)

def extract_sitemap_and_meta_tags(client, user, progress_callback=None):
    """
    Extract sitemap and meta tags from a client's website and save to cloud storage.
    
    Args:
        client: The client instance
        user: The user instance
        progress_callback: Optional callback function for progress reporting
        
    Returns:
        str: The relative path to the saved file
    """
    try:
        base_url = client.website_url.rstrip('/')  # Remove trailing slash if present
        fqdn = urlparse(base_url).netloc
        date_str = datetime.now().strftime("%y-%m-%d")
        file_name = f"{fqdn}-{date_str}.csv"
        relative_path = os.path.join(str(user.id), 'meta-tags', file_name)

        # Use SitemapRetrieverTool to get URLs
        sitemap_retriever = SitemapRetrieverTool()
        
        if progress_callback:
            progress_callback("Finding sitemaps and crawling website")
        
        # Set a higher max_pages value for more comprehensive crawling
        # Using CSV output format
        result = sitemap_retriever._run(url=base_url, user_id=user.id, max_pages=10000, output_format="json")
        result_data = json.loads(result)
        
        urls_to_visit = set()
        
        # Extract URLs from the sitemap result
        if result_data.get("success", False):
            urls = result_data.get("urls", [])
            for url_data in urls:
                if "loc" in url_data:
                    urls_to_visit.add(url_data["loc"])
        
        # If no URLs found, start with the base URL
        if not urls_to_visit:
            logger.warning(f"No URLs found in sitemap for {base_url}, using base URL")
            urls_to_visit.add(base_url)
        
        total_urls = len(urls_to_visit)
        logger.info(f"Found {total_urls} URLs to process for {base_url}")
        
        if progress_callback:
            progress_callback("Processing URLs", urls_found=total_urls, total_urls=total_urls)
        
        visited_urls = set()
        urls_processed = 0

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
                
                if progress_callback:
                    urls_processed += 1
                    progress_callback(f"Processing URL: {url}", 
                                    urls_processed=urls_processed, 
                                    total_urls=total_urls)
                
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

                    # Also extract links for additional crawling if needed
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
                logger.error(f"Error processing URL {url}: {str(e)}")

        if progress_callback:
            progress_callback("Saving results to file")
            
        # Get the full content as a string first
        content_str = output.getvalue()
        output.close()
        
        # Save using SecureFileStorage with explicit Content-Length
        content = ContentFile(content_str.encode('utf-8'))
        saved_path = meta_tag_storage._save(relative_path, content)

        # Log the activity
        user_activity_tool.run(user, 'create', f"Created meta tags snapshot for client: {client.name}", 
                             client=client, details={'file_name': file_name})

        return relative_path

    except Exception as e:
        logger.error(f"Error in extract_sitemap_and_meta_tags: {str(e)}", exc_info=True)
        raise

def extract_sitemap_and_meta_tags_from_url(url, user, output_file=None, progress_callback=None):
    """
    Extract sitemap and meta tags from a URL and save to cloud storage.
    
    Args:
        url: The URL to extract from
        user: The user instance
        output_file: Optional specific output file path to use
        progress_callback: Optional callback function for progress reporting
        
    Returns:
        str: The relative path to the saved file
    """
    try:
        base_url = url.rstrip('/')
        fqdn = urlparse(base_url).netloc
        
        # Use provided output_file or generate one
        if not output_file:
            date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{fqdn.replace('.', '_')}_{date_str}.csv"
            relative_path = f"{user.id}/meta-tags/{filename}"
        else:
            # If output_file is provided, use it as is (assumes it's a relative path)
            relative_path = output_file

        # Use SitemapRetrieverTool to get URLs
        sitemap_retriever = SitemapRetrieverTool()
        
        if progress_callback:
            progress_callback("Finding sitemaps and crawling website")
            
        # Set a higher max_pages value for more comprehensive crawling
        # Using JSON output format for the tool (we'll convert to CSV)
        result = sitemap_retriever._run(url=base_url, user_id=user.id, max_pages=10000, output_format="json")
        result_data = json.loads(result)
        
        urls_to_visit = set()
        
        # Extract URLs from the sitemap result
        if result_data.get("success", False):
            urls = result_data.get("urls", [])
            for url_data in urls:
                if "loc" in url_data:
                    urls_to_visit.add(url_data["loc"])
        
        # If no URLs found, start with the base URL
        if not urls_to_visit:
            logger.warning(f"No URLs found in sitemap for {base_url}, using base URL")
            urls_to_visit.add(base_url)
        
        total_urls = len(urls_to_visit)
        logger.info(f"Found {total_urls} URLs to process for {base_url}")
        
        if progress_callback:
            progress_callback("Processing URLs", urls_found=total_urls, total_urls=total_urls)
            
        visited_urls = set()
        urls_processed = 0

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
                
                if progress_callback:
                    urls_processed += 1
                    progress_callback(f"Processing URL: {url}", 
                                    urls_processed=urls_processed, 
                                    total_urls=total_urls)
                
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

                    # Write to CSV
                    writer.writerow(meta_tags)

                    # Also extract links for additional crawling if needed
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
                logger.error(f"Error processing URL {url}: {str(e)}")
        
        if progress_callback:
            progress_callback("Saving results to file")
        
        # Get the full content as a string first
        content_str = output.getvalue()
        output.close()
        
        # Save using SecureFileStorage with explicit Content-Length
        content = ContentFile(content_str.encode('utf-8'))
        saved_path = meta_tag_storage._save(relative_path, content)
        
        # Log the activity without a client
        user_activity_tool.run(user, 'create', f"Created meta tags snapshot for URL: {url}", 
                             details={'file_name': os.path.basename(relative_path)})

        return saved_path

    except Exception as e:
        logger.error(f"Error in extract_sitemap_and_meta_tags_from_url: {str(e)}", exc_info=True)
        raise
