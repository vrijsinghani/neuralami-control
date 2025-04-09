from apps.agents.tools.website_distiller_tool.website_distiller_tool import WebsiteDistillerTool
import json

# Create an instance of the tool
tool = WebsiteDistillerTool()

# Run the tool with a test URL
result = tool._run(
    website_url="https://www.steamwayfloortoceiling.com",
    max_pages=5,
    max_depth=2,
    detail_level="comprehensive"
)

# Parse the result
try:
    parsed_result = json.loads(result)
    print("Successfully parsed result as JSON")
    
    # Print the result summary
    if "error" in parsed_result:
        print(f"Error: {parsed_result['error']}")
        print(f"Message: {parsed_result.get('message', 'No message')}")
    else:
        print("Success!")
        print(f"Source URL: {parsed_result.get('source_url')}")
        print(f"Total pages: {parsed_result.get('total_pages')}")
        
        # Print a snippet of the processed content
        content = parsed_result.get('processed_content', '')
        if content:
            print(f"\nContent snippet (first 200 chars): {content[:200]}...")
        else:
            print("No content found in result")
            
except json.JSONDecodeError as e:
    print(f"Failed to parse result as JSON: {e}")
    print(f"Raw result: {result}")
