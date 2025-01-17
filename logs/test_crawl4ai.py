import requests
import json
import time

def test_crawl():
    print("\nStarting test crawl...")
    base_url = "http://192.168.1.160:11235"
    api_token = "crawl4aiNeuralami1"
    url_to_test = ["https://crazygatorairboats.com","https://neuralami.com"]
    
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    request = {
        "urls": [url_to_test],  # Changed to list format
        "priority": 10,
    }
    healthcheck = requests.get(f"{base_url}/health")
    print(f"testing health: {healthcheck.json()}")
    
    # Submit crawl
    print(f"\nSubmitting request: {json.dumps(request, indent=2)}")
    response = requests.post(f"{base_url}/crawl", json=request, headers=headers)
    task_id = response.json()["task_id"]
    print(f"Got task ID: {task_id}")
    
    # Poll for result
    while True:
        result = requests.get(f"{base_url}/task/{task_id}", headers=headers)
        status = result.json()
        print(f"\nCurrent status response:")
        print(json.dumps(status, indent=2))
       
        if status["status"] == "completed":
            # Get the first result since we only submitted one URL
            first_result = status['results'][0]
            content = first_result['markdown']
            links_data = first_result.get('links', {})
            internal_links = links_data.get('internal', [])
            external_links = links_data.get('external', [])
            
            print(f"\nCrawl completed!")
            print(f"Content length: {len(content)}")
            print(f"Internal pages found: {len(internal_links)}")
            print(f"External pages found: {len(external_links)}")
            print("\nInternal Links:")
            for link in internal_links:
                print(f"- {link.get('href', 'N/A')} ({link.get('text', 'No text')})")
            print("\nExternal Links:")
            for link in external_links:
                print(f"- {link.get('href', 'N/A')} ({link.get('text', 'No text')})")
            
            with open('test.txt', 'w', encoding='utf-8') as f:
                f.write(content)
            print("\nMarkdown content saved to test.txt")
            break
            
        elif status["status"] == "failed":
            print(f"\nTask failed: {status.get('error')}")
            break
            
        time.sleep(2)

if __name__ == "__main__":
    test_crawl()
