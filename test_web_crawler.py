from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool

# Create an instance of the tool
tool = WebCrawlerTool()

# Run the tool with a test URL
result = tool._run(
    start_url="https://neuralami.com",
    output_format="text,metadata",
    max_pages=1,
    max_depth=1
)

# Print the raw result type and content
print("Result type:", type(result))
print("Raw result:", result)

# Try to parse the result if it's a string
if isinstance(result, str):
    print("Result is a string with length:", len(result))
    if result.startswith("{") and result.endswith("}"):
        print("Result appears to be a JSON string")
        import json
        try:
            parsed_result = json.loads(result)
            print("Successfully parsed JSON")
            print("Keys:", list(parsed_result.keys()))
        except json.JSONDecodeError as e:
            print("Failed to parse JSON:", str(e))
else:
    # Check if the result contains content
    print("Success:", result.get("status") == "success")
    print("Number of pages:", len(result.get("results", [])))
    if result.get("results"):
        first_page = result["results"][0]
        print("First page URL:", first_page.get("url"))
        print("Content types:", list(first_page.keys()))
        if "metadata" in first_page:
            print("Metadata keys:", list(first_page["metadata"].keys()))
    else:
        print("No results found")
