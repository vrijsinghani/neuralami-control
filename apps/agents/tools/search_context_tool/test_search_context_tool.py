import logging
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, project_root)

# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')  # Adjust this to your project's settings module
import django
django.setup()

from apps.agents.tools.search_context_tool.search_context_tool import SearchContextTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_search_context():
  # Initialize the tool
  search_tool = SearchContextTool()

  # Test question
  test_question = "as of october 29, 2024 what are the latest flooring trends in ottumwa that consumers are looking for and elaborate on the reasons why?"
  
  logger.info(f"Starting search context analysis for question: {test_question}")
  print(f"Starting search context analysis for question: {test_question}")
  
  try:
      # Get results
      result = search_tool._run(test_question)
      
      # Log and print the results
      logger.info("Search Context Results:")
      logger.info(result)
      print("\nSearch Context Results:")
      print(result)
      
  except Exception as e:
      logger.error(f"Error during search context analysis: {str(e)}")
      print(f"Error: {str(e)}")

if __name__ == "__main__":
  test_search_context()