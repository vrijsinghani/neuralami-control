from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter
from urllib.parse import urlparse, urljoin
import json
import time

# Function to crawl a website
def crawl_website(start_url, max_pages=3, max_depth=2):
    # Initialize the crawler state
    visited_urls = set()
    url_queue = [(start_url, 0)]  # (url, depth)
    results = []
    pages_crawled = 0
    
    # Extract and normalize the domain
    parsed_url = urlparse(start_url)
    base_domain = parsed_url.netloc
    if base_domain.startswith('www.'):
        base_domain = base_domain[4:]
    
    # Create a Playwright adapter instance
    adapter = PlaywrightAdapter()
    
    # Process URLs until we reach the maximum number of pages or run out of URLs
    while url_queue and pages_crawled < max_pages:
        # Get the next URL to process
        url, depth = url_queue.pop(0)
        
        # Skip if we've already visited this URL
        if url in visited_urls:
            continue
        
        print(f"Processing URL: {url} at depth {depth}")
        
        # Scrape the URL
        try:
            result = adapter.scrape(
                url=url,
                formats=["text", "metadata", "links"],
                timeout=60000,
                cache=True,
                stealth=True
            )
            
            # Check if we have a valid result
            if result and "text" in result and "metadata" in result:
                # Create a page result with the content
                page_result = {
                    "url": url,
                    "title": result.get("metadata", {}).get("title", ""),
                    "success": True,
                    "text": result.get("text", ""),
                    "metadata": result.get("metadata", {})
                }
                
                # Add the page to the results
                results.append(page_result)
                pages_crawled += 1
                
                # Extract links for further crawling
                if "links" in result and depth < max_depth:
                    links = result["links"]
                    for link_item in links:
                        if isinstance(link_item, dict) and "href" in link_item:
                            link_url = link_item["href"]
                            
                            # Normalize the URL
                            link_url = urljoin(url, link_url)
                            
                            # Check if we should crawl this URL
                            should_crawl = True
                            
                            # Check if URL is within the same domain
                            link_domain = urlparse(link_url).netloc
                            if link_domain.startswith('www.'):
                                link_domain = link_domain[4:]
                            if link_domain != base_domain:
                                should_crawl = False
                            
                            # Check if URL has already been visited or queued
                            if link_url in visited_urls or any(link_url == u for u, _ in url_queue):
                                should_crawl = False
                            
                            if should_crawl:
                                # Add URL to queue
                                url_queue.append((link_url, depth + 1))
        except Exception as e:
            print(f"Failed to scrape {url}: {str(e)}")
        
        # Add the URL to visited URLs
        visited_urls.add(url)
        
        # Apply delay between requests
        time.sleep(1.0)
    
    # Return the result
    return {
        "status": "success",
        "warning": "No valid content found" if not results else None,
        "start_url": start_url,
        "total_pages": len(results),
        "results": results
    }

# Crawl the website
result = crawl_website("https://neuralami.com", max_pages=3, max_depth=2)

# Print the result summary
print("\nStatus:", result.get("status"))
print("Total pages:", result.get("total_pages"))
print("Warning:", result.get("warning"))

# Print the pages
if result.get("results"):
    print("\nPages:")
    for i, page in enumerate(result["results"]):
        print(f"{i+1}. {page.get('url')} - {page.get('title')}")
