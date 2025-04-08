from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter
import json

# Create an instance of the adapter
adapter = PlaywrightAdapter()

# Scrape a URL directly
result = adapter.scrape(
    url="https://neuralami.com",
    formats=["text", "metadata", "links"],
    timeout=60000,
    cache=True,
    stealth=True
)

# Print the raw result
print("Result type:", type(result))
print("Result keys:", list(result.keys()))

# Create a page result with the content
page_result = {
    "url": "https://neuralami.com",
    "title": result.get("metadata", {}).get("title", ""),
    "success": True
}

# Add the content to the page result
for content_type in ["text", "html", "metadata", "links"]:
    if content_type in result:
        page_result[content_type] = result[content_type]

# Create the final result
final_result = {
    "status": "success",
    "start_url": "https://neuralami.com",
    "total_pages": 1,
    "results": [page_result]
}

# Print the final result
print("\nFinal result:")
print(json.dumps(final_result, indent=2))
