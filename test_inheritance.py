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

# Import the BaseTool classes
from apps.agents.utils.minimal_tools import BaseTool as CustomBaseTool
from crewai.tools import BaseTool as CrewAIBaseTool
from pydantic import Field

# Test simple inheritance
def test_inheritance():
    print("\n=== Testing BaseTool Inheritance ===")
    print(f"CustomBaseTool: {CustomBaseTool}")
    print(f"CrewAIBaseTool: {CrewAIBaseTool}")
    
    # Check if CustomBaseTool is a subclass of CrewAIBaseTool
    print(f"CustomBaseTool is a subclass of CrewAIBaseTool: {issubclass(CustomBaseTool, CrewAIBaseTool)}")
    
    # Create a minimal tool using our custom BaseTool with proper type annotations
    class MinimalTool(CustomBaseTool):
        name: str = Field(default="MinimalTool")
        description: str = Field(default="A minimal tool for testing")
        
        def _run(self, *args: Any, **kwargs: Dict[str, Any]) -> str:
            return "Minimal tool ran successfully"
    
    # Create an instance
    minimal_tool = MinimalTool()
    print(f"Created tool instance: {minimal_tool}")
    
    # Check if it's an instance of both classes
    print(f"Is instance of CustomBaseTool: {isinstance(minimal_tool, CustomBaseTool)}")
    print(f"Is instance of CrewAIBaseTool: {isinstance(minimal_tool, CrewAIBaseTool)}")
    
    # Check Method Resolution Order (MRO)
    print(f"MinimalTool MRO: {[cls.__name__ for cls in MinimalTool.__mro__]}")
    
    # Test with CrewAI Task if available
    try:
        from crewai.tasks import Task as CrewAITask
        print("\n=== Testing with CrewAI Task ===")
        
        task = CrewAITask(
            description="Test task", 
            expected_output="Test output",
            tools=[minimal_tool]
        )
        print(f"Successfully created CrewAI Task with our custom tool: {task}")
        print("Task validation passed! This confirms our approach works with CrewAI.")
    except ImportError:
        print("Could not import CrewAITask for testing")
    except Exception as e:
        print(f"Error creating CrewAI Task: {str(e)}")

# Test with real tools from the database
def test_real_tool():
    print("\n=== Testing with Real Tools ===")
    try:
        from apps.agents.models import Tool
        from apps.agents.tasks.utils.tools import load_tool_in_task
        
        # Get first available tool
        tool = Tool.objects.first()
        if not tool:
            print("No tools found in the database")
            return
            
        print(f"Testing with tool: {tool.name}")
        result = load_tool_in_task(tool)
        print(f"Result type: {type(result)}")
        print(f"Is instance of CrewAIBaseTool: {isinstance(result, CrewAIBaseTool)}")
        print(f"Success with tool: {tool.name}!")
    except Exception as e:
        print(f"Error testing real tool: {str(e)}")

if __name__ == "__main__":
    print("Starting tests...")
    test_inheritance()
    test_real_tool()
    print("\nTests completed!") 