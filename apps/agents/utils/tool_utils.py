import os
import importlib
from crewai.tools import BaseTool as CrewAIBaseTool
from langchain.tools import BaseTool as LangChainBaseTool
import logging
import crewai_tools
from typing import Optional, Type
from django.core.cache import cache
from pydantic import BaseModel
from crewai.tools import BaseTool

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
    # Handle dot-notation paths like 'directory.file'
    if '.' in tool_path and not tool_path.endswith('.py'):
        parts = tool_path.split('.')
        # If it's a pattern like 'scrapper_tool.scrapper_tool', use just the directory
        if len(parts) == 2 and parts[0] == parts[1]:
            module_path = f"apps.agents.tools.{parts[0]}"
            logger.debug(f"Dot-notation with duplicate name detected. Using path: {module_path}")
        else:
            module_path = f"apps.agents.tools.{tool_path}"
            logger.debug(f"Using full dot-notation path: {module_path}")
    else:
        module_path = f"apps.agents.tools.{tool_path}"
        logger.debug(f"Using standard path: {module_path}")
        
    if module_path.endswith('.py'):
        module_path = module_path[:-3]
    
    try:
        module = importlib.import_module(module_path)
        tool_classes = []
        
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and name.endswith('Tool'):
                try:
                    if issubclass(obj, (CrewAIBaseTool, LangChainBaseTool)) or (hasattr(obj, '_run') and callable(getattr(obj, '_run'))):
                        if not any(issubclass(other, obj) and other != obj for other in module.__dict__.values() if isinstance(other, type)):
                            tool_classes.append(obj)
                except TypeError:
                    # This can happen if obj is not a class or doesn't inherit from the expected base classes
                    logger.warning(f"Skipping {name} as it's not a valid tool class")
        
        logger.debug(f"Found tool classes for {tool_path}: {[cls.__name__ for cls in tool_classes]}")
        return tool_classes
    except ImportError as e:
        logger.error(f"Failed to import module {module_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting tool classes from {module_path}: {e}")
        return []

def get_tool_description(tool_class_obj):
    """Get a tool's description, with special handling for various tool types."""
    try:
        if hasattr(tool_class_obj, 'description') and tool_class_obj.description:
            # For CrewAI tools
            return tool_class_obj.description
        elif hasattr(tool_class_obj, 'description_for_model') and tool_class_obj.description_for_model:
            # For some LangChain tools
            return tool_class_obj.description_for_model
        else:
            # Fallback to docstring
            return tool_class_obj.__doc__ or "No description available"
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
                    issubclass(attr, CrewAIBaseTool) or 
                    issubclass(attr, LangChainBaseTool)
                ) and attr not in (CrewAIBaseTool, LangChainBaseTool):
                    return attr
                    
            logger.error(f"No tool class found in {module_path}")
            return None
    except ImportError as e:
        logger.error(f"Error importing tool module {tool_class}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting tool class object: {e}")
        return None

def load_tool(tool_model) -> Optional[CrewAIBaseTool]:
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
        if issubclass(tool_class, CrewAIBaseTool):
            # CrewAI tool - instantiate directly
            return tool_class()
        elif issubclass(tool_class, LangChainBaseTool):
            # LangChain tool - needs wrapper
            langchain_tool = tool_class()
            
            # Create a wrapper class that adapts the LangChain tool to CrewAI
            class WrappedLangChainTool(CrewAIBaseTool):
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