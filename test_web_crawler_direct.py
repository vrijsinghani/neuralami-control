from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter

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

# Print the raw result type and content
print("Result type:", type(result))
print("Result keys:", list(result.keys()))

if "data" in result:
    print("Data keys:", list(result["data"].keys()))
    
    # Check if we have metadata
    if "metadata" in result["data"]:
        print("Metadata keys:", list(result["data"]["metadata"].keys()))
        print("Title:", result["data"]["metadata"].get("title", ""))
    
    # Check if we have text
    if "text" in result["data"]:
        print("Text length:", len(result["data"]["text"]))
        print("Text preview:", result["data"]["text"][:100] + "...")
    
    # Check if we have links
    if "links" in result["data"]:
        print("Links count:", len(result["data"]["links"]))
        print("First 3 links:", result["data"]["links"][:3])
