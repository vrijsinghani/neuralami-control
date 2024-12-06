import logging
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, project_root)

from apps.agents.tools.browser_tool.browser_tool import BrowserTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_browser_tool():
    # Initialize the tool
    browser = BrowserTool()

    # Test get_content
    test_url = "https://brandon.neuralami.com"
    logger.info(f"Testing get_content for {test_url}")
    content = browser.get_content(test_url)
    logger.info(f"Content length: {len(content)}")
    logger.info(f"Content preview: {content[:200]}...")
    print(content[:200])

    # Test get_links
    logger.info(f"Testing get_links for {test_url}")
    links = browser.get_links(test_url)
    logger.info(f"Number of links found: {len(links)}")
    logger.info(f"Links: {links}")
    print(links)
if __name__ == "__main__":
    test_browser_tool()
