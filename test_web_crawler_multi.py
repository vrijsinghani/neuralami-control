from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool
import json

# Create an instance of the tool
tool = WebCrawlerTool()

# Run the tool with a test URL
result = tool._run(
    start_url="https://neuralami.com",
    output_format="text,metadata",
    max_pages=3,
    max_depth=2
)

# Parse the result
parsed_result = json.loads(result)

# Print the result summary
print("Status:", parsed_result.get("status"))
print("Total pages:", parsed_result.get("total_pages"))
print("Warning:", parsed_result.get("warning"))

# Print the pages
if parsed_result.get("results"):
    print("\nPages:")
    for i, page in enumerate(parsed_result["results"]):
        print(f"{i+1}. {page.get('url')} - {page.get('title')}")
