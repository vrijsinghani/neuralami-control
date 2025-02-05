import requests
import json
import time

def test_crawl():
    print("\nStarting test crawl...")
    base_url = "http://192.168.1.160:11235"
    api_token = "crawl4aiNeuralami1"
    url_to_test = "https://crazygatorairboats.com"  # Single URL for testing
    
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    
    # Create proper request payload matching SpiderRequest model
    request = {
        "url": url_to_test,  # Single URL instead of list
        "max_depth": 3,
        "max_pages": 100,
        "batch_size": 10,
        "crawler_params": {
            "headless": True,
            "page_timeout": 30000,
            "simulate_user": True,
            "magic": True,
            "remove_overlay_elements": True
        },
        "extraction_config": {
            "type": "basic",
            "params": {
                "word_count_threshold": 10,
                "only_text": True,
                "bypass_cache": False,
                "process_iframes": True,
                "excluded_tags": ["nav", "aside", "footer"]
            }
        }
    }
    
    # Test health endpoint
    healthcheck = requests.get(f"{base_url}/health")
    print(f"Health check response: {healthcheck.json()}")
    
    # Submit spider crawl request
    print(f"\nSubmitting request: {json.dumps(request, indent=2)}")
    response = requests.post(
        f"{base_url}/spider", 
        json=request, 
        headers=headers
    )
    
    if not response.ok:
        print(f"Error response: {response.text}")
        return
        
    result = response.json()
    print(f"Initial response: {json.dumps(result, indent=2)}")
    
    # Process results
    if "results" in result:
        crawled_count = result.get("crawled_count", 0)
        failed_count = result.get("failed_count", 0)
        max_depth = result.get("max_depth_reached", 0)
        
        print(f"\nCrawl completed!")
        print(f"Pages crawled: {crawled_count}")
        print(f"Failed pages: {failed_count}")
        print(f"Max depth reached: {max_depth}")
        
        # Save first page content as example
        if result["results"]:
            first_url = next(iter(result["results"]))
            first_result = result["results"][first_url]
            content = first_result.get("markdown", "")
            
            with open('test.txt', 'w', encoding='utf-8') as f:
                f.write(f"URL: {first_url}\n\n")
                f.write(content)
            print("\nFirst page content saved to test.txt")
            
            # Print some stats about the first page
            print(f"\nFirst page details:")
            print(f"URL: {first_url}")
            print(f"Content length: {len(content)}")
            if "links" in first_result:
                internal_links = len(first_result["links"].get("internal", []))
                external_links = len(first_result["links"].get("external", []))
                print(f"Internal links: {internal_links}")
                print(f"External links: {external_links}")
    else:
        print(f"Unexpected response format: {result}")

if __name__ == "__main__":
    test_crawl()
