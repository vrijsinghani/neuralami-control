#!/usr/bin/env python
import os
import sys
import django
from django.conf import settings
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Now import our module
from apps.agents.tasks.utils.tools import CrewAIToolAdapter
from crewai.tools import BaseTool as CrewAIBaseTool

# Create a mock tool instance
class DummyTool:
    def __init__(self):
        self.name = "DummyTool"
        self.description = "A dummy tool for testing"
    
    def _run(self, *args, **kwargs):
        return f"DummyTool executed with args={args}, kwargs={kwargs}"

# Create a test for our adapter
def test_adapter():
    print("Creating dummy tool...")
    dummy_tool = DummyTool()
    
    print("Creating adapter...")
    adapter = CrewAIToolAdapter(name="TestAdapter", description="Test adapter description", tool_instance=dummy_tool)
    
    print("Adapter created successfully with name:", adapter.name)
    print("Testing _run method...")
    result = adapter._run("test input")
    print("Result:", result)
    
    # Test if this adapter is recognized as a CrewAIBaseTool
    print(f"Is instance of CrewAIBaseTool? {isinstance(adapter, CrewAIBaseTool)}")
    
    print("Test passed!")

if __name__ == "__main__":
    print("Starting test...")
    test_adapter() 