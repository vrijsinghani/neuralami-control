#!/usr/bin/env python
import os
import sys
import django
import inspect
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Now import our module
from apps.agents.tasks.utils.tools import ToolAdapter
from apps.agents.tools.base_tool import BaseTool as CrewAIBaseTool

# Import directly from crewai
try:
    from crewai.tools import BaseTool as DirectCrewAIBaseTool
    print("Successfully imported BaseTool directly from crewai.tools")
except ImportError:
    print("Could not import BaseTool directly from crewai.tools")
    # Try another import path
    try:
        from crewai import BaseTool as AlternateCrewAIBaseTool
        print("Successfully imported BaseTool directly from crewai")
        DirectCrewAIBaseTool = AlternateCrewAIBaseTool
    except ImportError:
        DirectCrewAIBaseTool = None
        print("Could not import BaseTool directly from crewai")

# Check the inheritance chain
print("\n=== Checking Tool Class Inheritance ===")
print(f"CrewAIBaseTool (our import): {CrewAIBaseTool}")
if DirectCrewAIBaseTool:
    print(f"DirectCrewAIBaseTool (direct import): {DirectCrewAIBaseTool}")
    print(f"Are they the same class? {CrewAIBaseTool is DirectCrewAIBaseTool}")

# Check the module and path of each class
print("\n=== Checking Class Modules and Paths ===")
print(f"CrewAIBaseTool module: {CrewAIBaseTool.__module__}")
print(f"CrewAIBaseTool file: {inspect.getfile(CrewAIBaseTool)}")
if DirectCrewAIBaseTool:
    print(f"DirectCrewAIBaseTool module: {DirectCrewAIBaseTool.__module__}")
    print(f"DirectCrewAIBaseTool file: {inspect.getfile(DirectCrewAIBaseTool)}")

# Create a more direct, minimal subclass to test
class MinimalBaseTool(CrewAIBaseTool):
    name = "MinimalTool"
    description = "A minimal tool for testing"
    
    def _run(self, *args, **kwargs):
        return "Minimal tool ran successfully"

print("\n=== Testing Minimal Tool ===")
minimal_tool = MinimalBaseTool()
print(f"Minimal tool created successfully: {minimal_tool}")
print(f"Minimal tool inherits from CrewAIBaseTool? {isinstance(minimal_tool, CrewAIBaseTool)}")
if DirectCrewAIBaseTool:
    print(f"Minimal tool inherits from DirectCrewAIBaseTool? {isinstance(minimal_tool, DirectCrewAIBaseTool)}")

# Check the MRO (Method Resolution Order)
print("\n=== Checking Method Resolution Order (MRO) ===")
print(f"MinimalBaseTool MRO: {[cls.__name__ for cls in MinimalBaseTool.__mro__]}")

# Test importing the CrewAI Task class to check validation
try:
    from crewai.tasks import Task as CrewAITask
    print("\n=== Importing CrewAI Task Class ===")
    print(f"Successfully imported CrewAITask: {CrewAITask}")
    
    # Try to create a task with our minimal tool
    try:
        task = CrewAITask(
            description="Test task",
            expected_output="Test output", 
            tools=[minimal_tool]
        )
        print(f"Successfully created task with minimal tool: {task}")
    except Exception as e:
        print(f"Error creating task with minimal tool: {str(e)}")
        
except ImportError:
    print("Could not import CrewAITask")

if __name__ == "__main__":
    print("Script completed") 