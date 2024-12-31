# tools_list.py
import os
from django.conf import settings
import django
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')  # Replace with your project name
django.setup()

from apps.agents.models import Tool

def list_tools_to_file():
    tools = Tool.objects.all()
    with open('tools.txt', 'w') as file:
        for tool in tools:
            file.write(f"Name: {tool.name}\nDescription: {tool.description}\n\n")

if __name__ == "__main__":
    list_tools_to_file()