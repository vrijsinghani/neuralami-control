import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Import the tool
from apps.agents.tools.seo_audit_tool.seo_audit_tool import SEOAuditTool

# Create a progress callback function
def progress_callback(data):
    print(f"Progress: {data.get('percent_complete')}%, Status: {data.get('status')}")
    print(f"Pages analyzed: {data.get('pages_analyzed')}, Issues found: {data.get('issues_found')}")
    print("-" * 80)

# Create and run the tool
tool = SEOAuditTool()
website = "https://www.accel-golf.com"
result = tool._run(
    website=website,
    max_pages=10,
    check_external_links=False,
    crawl_delay=1.0,
    progress_callback=progress_callback,
    crawl_mode="auto"
)

# Print summary of results
print("\n--- Audit Results Summary ---")
print(f"Total issues found: {sum(len(result.get(k, [])) for k in result if k.endswith('_issues'))}")
print(f"Pages analyzed: {len(result.get('page_analysis', []))}")
print(f"Audit time: {result.get('summary', {}).get('total_audit_time_seconds', 0):.2f} seconds")
