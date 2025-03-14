#!/usr/bin/env python
import os
import django
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Now import what we need
from apps.agents.models import Tool
from apps.agents.tasks.utils.tools import load_tool_in_task
from crewai.tools import BaseTool as CrewAIBaseTool

def test_real_tool():
    print("Checking for Google tools in the database...")
    tools = Tool.objects.filter(tool_class__in=['google_analytics_tool', 'google_search_console_tool'])
    tool_count = tools.count()
    print(f"Found {tool_count} Google tools")
    
    if tool_count == 0:
        print("No Google tools found in the database")
        return
    
    # Try with Google Analytics tool
    ga_tool = Tool.objects.filter(tool_class='google_analytics_tool').first()
    if ga_tool:
        print(f"\nTesting with Google Analytics tool: {ga_tool.name}")
        try:
            result = load_tool_in_task(ga_tool)
            print(f"Result type: {type(result)}")
            print(f"Is instance of CrewAIBaseTool: {isinstance(result, CrewAIBaseTool)}")
            print("Success with Google Analytics tool!")
        except Exception as e:
            print(f"Error with Google Analytics tool: {str(e)}")
    
    # Try with Search Console tool
    sc_tool = Tool.objects.filter(tool_class='google_search_console_tool').first()
    if sc_tool:
        print(f"\nTesting with Search Console tool: {sc_tool.name}")
        try:
            result = load_tool_in_task(sc_tool)
            print(f"Result type: {type(result)}")
            print(f"Is instance of CrewAIBaseTool: {isinstance(result, CrewAIBaseTool)}")
            print("Success with Search Console tool!")
        except Exception as e:
            print(f"Error with Search Console tool: {str(e)}")

if __name__ == "__main__":
    print("Starting test...")
    test_real_tool()
    print("Test completed!") 