#!/usr/bin/env python
import os
import sys
import django
import logging
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Import the required classes
from crewai.tools import BaseTool as CrewAIBaseTool
from apps.agents.models import Tool
from apps.agents.tasks.utils.tools import load_tool_in_task
from crewai.tasks import Task as CrewAITask

def test_google_tools():
    print("\n=== Testing Google Tools ===")
    
    # Find all Google tools
    google_tools = Tool.objects.filter(
        tool_class__in=['google_analytics_tool', 'google_search_console_tool']
    )
    
    if not google_tools.exists():
        print("No Google tools found. Creating a mock Google tool...")
        
        # Create a mock tool using CrewAIBaseTool
        class MockGoogleTool(CrewAIBaseTool):
            name: str = "MockGoogleAnalyticsTool"
            description: str = "A mock Google Analytics tool for testing"
            
            def _run(self, *args: Any, **kwargs: Dict[str, Any]) -> str:
                return "Mock Google Analytics data"
        
        mock_tool = MockGoogleTool()
        print(f"Created mock tool: {mock_tool}")
        
        # Test with CrewAI Task
        try:
            task = CrewAITask(
                description="Test Google Analytics task", 
                expected_output="Analytics data",
                tools=[mock_tool]
            )
            print(f"Successfully created CrewAI Task with mock Google tool: {task}")
            print("Task validation passed with mock tool!")
        except Exception as e:
            print(f"Error creating CrewAI Task with mock tool: {str(e)}")
        
        return
    
    # If we have real Google tools, test them
    print(f"Found {google_tools.count()} Google tools")
    
    for tool in google_tools:
        print(f"\nTesting Google tool: {tool.name}")
        try:
            result = load_tool_in_task(tool)
            print(f"Result type: {type(result)}")
            print(f"Is instance of CrewAIBaseTool: {isinstance(result, CrewAIBaseTool)}")
            
            # Test with CrewAI Task if possible
            try:
                task = CrewAITask(
                    description=f"Test {tool.name} task", 
                    expected_output="Google data",
                    tools=[result]
                )
                print(f"Successfully created CrewAI Task with {tool.name}!")
                print("Task validation passed! This confirms our approach works with CrewAI.")
            except Exception as e:
                print(f"Error creating CrewAI Task: {str(e)}")
            
        except Exception as e:
            print(f"Error loading tool {tool.name}: {str(e)}")

if __name__ == "__main__":
    print("Starting Google tool tests...")
    test_google_tools()
    print("\nTests completed!") 