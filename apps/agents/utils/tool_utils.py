import os
import importlib
from apps.agents.utils.minimal_tools import BaseTool
from langchain.tools import BaseTool as LangChainBaseTool
import logging
import re
from typing import Optional, Type
from django.core.cache import cache
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def get_available_tools():
    tools_dir = os.path.join('apps', 'agents', 'tools')
    available_tools = []

    for root, dirs, files in os.walk(tools_dir):
        for item in dirs + files:
            if item.endswith('.py') and not item.startswith('__'):
                rel_path = os.path.relpath(os.path.join(root, item), tools_dir)
                module_path = os.path.splitext(rel_path)[0].replace(os.path.sep, '.')
                available_tools.append(module_path)

    return available_tools

def get_tool_classes(tool_path):
    module_path = f"apps.agents.tools.{tool_path}"
    
    try:
        module = importlib.import_module(module_path)
        tool_classes = []
        
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and (
                issubclass(attr, BaseTool) or 
                issubclass(attr, LangChainBaseTool)
            ) and attr not in (BaseTool, LangChainBaseTool):
                # Return the class object instead of the name for compatibility with newer code
                tool_classes.append(attr)
                
        return tool_classes
    except ImportError as e:
        logger.error(f"Error importing tool module {module_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting tool classes from {module_path}: {e}")
        return []

def get_tool_description(tool_class_obj):
    """Get a tool's description, with special handling for various tool types."""
    try:
        # If we got a string (class name) instead of a class object, try to get the actual class
        if isinstance(tool_class_obj, str):
            logger.debug(f"Got string instead of class object: {tool_class_obj}")
            # Try to find the class in its module
            parts = tool_class_obj.split('.')
            module_name = '.'.join(parts[:-1]) if len(parts) > 1 else ''
            class_name = parts[-1]
            
            if not module_name:
                # If no module specified, assume it's in the current module
                module_path = f"apps.agents.tools.{tool_class_obj}"
                try:
                    module = importlib.import_module(module_path)
                    if hasattr(module, class_name):
                        tool_class_obj = getattr(module, class_name)
                except ImportError:
                    logger.warning(f"Could not import module {module_path}")
        
        # Clean up the description to avoid including parameter metadata
        description = None
        
        # If we were passed a class object, check for description attributes
        if isinstance(tool_class_obj, type):
            # For class definitions with "description" attribute (most BaseTool subclasses)
            if hasattr(tool_class_obj, 'description') and tool_class_obj.description:
                description = tool_class_obj.description
            # For some LangChain tools
            elif hasattr(tool_class_obj, 'description_for_model') and tool_class_obj.description_for_model:
                description = tool_class_obj.description_for_model
            # Try to get an instance and check its attributes
            else:
                try:
                    # Some tools store description in instances rather than class
                    instance = tool_class_obj()
                    if hasattr(instance, 'description') and instance.description:
                        description = instance.description
                    elif hasattr(instance, 'description_for_model') and instance.description_for_model:
                        description = instance.description_for_model
                except:
                    # If instantiation fails, continue to docstring fallback
                    pass
        
        # Fallback to docstring for any type of object
        if not description and hasattr(tool_class_obj, '__doc__') and tool_class_obj.__doc__:
            description = tool_class_obj.__doc__
        
        if not description:
            return "No description available"
            
        # Clean up the description - remove parameter details
        # If it contains parentheses with parameters, strip them out
        if '(' in description and ')' in description:
            # Check if it looks like "Tool Name(param1, param2) - Description"
            cleaned_desc = re.sub(r'\([^)]*\)', '', description)
            if ' - ' in cleaned_desc:
                # Keep only the part after " - "
                cleaned_desc = cleaned_desc.split(' - ', 1)[1].strip()
            description = cleaned_desc
            
        # Remove parameter lists that come after the main description
        if description.count('.') > 0:
            # If there are multiple sentences and the later ones look like parameter definitions
            first_part = description.split('.', 1)[0].strip() + '.'
            if len(first_part) > 20:  # Make sure it's a reasonable length
                description = first_part
        
        return description.strip()
    except Exception as e:
        logger.error(f"Error getting tool description: {e}")
        return "Description unavailable due to error"

def get_tool_class_obj(tool_class: str, tool_subclass: str = None) -> Type[BaseTool]:
    """
    Get the actual tool class object by name and optional subclass.
    
    Args:
        tool_class: The path to the tool module (e.g., 'web_search_tool')
        tool_subclass: Optional class name within the module
        
    Returns:
        The tool class object or None if not found
    """
    try:
        # Handle both formats: with or without .py extension
        tool_path = tool_class.replace('.py', '')
        
        # Import the module
        module_path = f"apps.agents.tools.{tool_path}"
        module = importlib.import_module(module_path)
        
        if tool_subclass:
            # If subclass specified, get that specific class
            if hasattr(module, tool_subclass):
                return getattr(module, tool_subclass)
            else:
                logger.error(f"Tool subclass {tool_subclass} not found in {module_path}")
                return None
        else:
            # Find the first available tool class
            for attr_name in dir(module):
                if attr_name.startswith('_'):
                    continue
                    
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and (
                    issubclass(attr, BaseTool) or 
                    issubclass(attr, LangChainBaseTool)
                ) and attr not in (BaseTool, LangChainBaseTool):
                    return attr
                    
            logger.error(f"No tool class found in {module_path}")
            return None
    except ImportError as e:
        logger.error(f"Error importing tool module {tool_class}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting tool class object: {e}")
        return None

def load_tool(tool_model) -> Optional[BaseTool]:
    """
    Load and instantiate a tool from the database model.
    Will adapt LangChain tools to CrewAI tools if needed.
    """
    try:
        # Get the tool class
        tool_class = get_tool_class_obj(tool_model.tool_class, tool_model.tool_subclass)
        if not tool_class:
            logger.error(f"Could not load tool class for {tool_model.tool_class}")
            return None
            
        # Handle different tool types
        if issubclass(tool_class, BaseTool):
            # CrewAI tool - instantiate directly
            return tool_class()
        elif issubclass(tool_class, LangChainBaseTool):
            # LangChain tool - needs wrapper
            langchain_tool = tool_class()
            
            # Create a wrapper class that adapts the LangChain tool to CrewAI
            class WrappedLangChainTool(BaseTool):
                name = tool_class.name
                description = get_tool_description(tool_class)
                
                def _run(self, *args, **kwargs):
                    # Forward the call to the LangChain tool
                    return langchain_tool._run(*args, **kwargs)
            
            return WrappedLangChainTool()
        else:
            logger.error(f"Unknown tool type for {tool_model.tool_class}")
            return None
    except Exception as e:
        logger.error(f"Error loading tool {tool_model.tool_class}: {e}")
        return None

def get_tool_info(tool_model):
    """
    Get basic information about a tool from its model.
    
    Args:
        tool_model: The tool model object from the database
        
    Returns:
        Dict with module_path and class_name
    """
    full_module_path = f"apps.agents.tools.{tool_model.tool_class}"
    
    return {
        'module_path': full_module_path,
        'class_name': tool_model.tool_subclass
    } 