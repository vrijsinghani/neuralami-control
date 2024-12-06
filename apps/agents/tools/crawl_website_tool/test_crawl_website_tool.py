import logging
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, project_root)

from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_crawl_website():
    # Initialize the tool
    crawler = CrawlWebsiteTool()

    # Test with a real website
    test_url = "https://proplankohio.com"
    logger.info(f"Starting crawl of {test_url}")
    print(f"Starting crawl of {test_url}")
    result = crawler._run(test_url)

    # Print the result
    logger.info(f"Crawl result for {test_url}:")
    logger.info(result)
    print(result)

    # You can add more assertions here to verify the output

if __name__ == "__main__":
    test_crawl_website()
