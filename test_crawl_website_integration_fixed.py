from apps.crawl_website.tasks import crawl_website_task
import json

# Test the crawl_website_task function
result_json = crawl_website_task(
    task_id="test_task_id",
    website_url="https://www.neuralami.com",
    user_id=1,
    max_pages=3,
    max_depth=2,
    include_patterns=None,
    exclude_patterns=None,
    output_format="text,metadata",
    save_file=False,
    save_as_csv=False
)

# Parse the result
result = json.loads(result_json)

# Print the result summary
print("Status:", result.get("status"))
print("Total pages:", result.get("total_pages"))
print("Warning:", result.get("warning"))

# Print the pages
if result.get("results"):
    print("\nPages:")
    for i, page in enumerate(result["results"]):
        print(f"{i+1}. {page.get('url')} - {page.get('title')}")
        
    # Check for duplicate URLs
    urls = [page.get('url') for page in result["results"]]
    unique_urls = set(urls)
    if len(urls) != len(unique_urls):
        print("\nWARNING: Duplicate URLs found!")
        for url in unique_urls:
            count = urls.count(url)
            if count > 1:
                print(f"URL: {url} appears {count} times")
    else:
        print("\nNo duplicate URLs found.")
