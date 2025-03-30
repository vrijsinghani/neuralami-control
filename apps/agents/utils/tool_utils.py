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
    """Get a tool's description, prioritizing direct attributes and docstrings."""
    try:
        # Ensure we have a class object if a name was passed
        if isinstance(tool_class_obj, str):
            logger.warning(f"get_tool_description received a string '{tool_class_obj}', expected a class object. Attempting to resolve.")
            return f"Error: Expected class object, got string '{tool_class_obj}'"

        tool_class_name = tool_class_obj.__name__ if isinstance(tool_class_obj, type) else str(tool_class_obj)
        logger.debug(f"Getting description for tool: {tool_class_name}")

        description = None
        raw_value = None # Variable to store the raw retrieved value

        # 1. Direct Class Attribute Access (Highest Priority)
        if isinstance(tool_class_obj, type):
            if hasattr(tool_class_obj, 'description'):
                raw_value = getattr(tool_class_obj, 'description')
                logger.debug(f"Raw value from class attribute 'description': type={type(raw_value)}, value='{str(raw_value)[:150]}...'")
                if isinstance(raw_value, str):
                    description = raw_value
                    logger.debug("Using description as direct class attribute")

            # 2. LangChain specific attribute
            if not description and hasattr(tool_class_obj, 'description_for_model'):
                raw_value = getattr(tool_class_obj, 'description_for_model')
                logger.debug(f"Raw value from class attribute 'description_for_model': type={type(raw_value)}, value='{str(raw_value)[:150]}...'")
                if isinstance(raw_value, str):
                    description = raw_value
                    logger.debug("Using description_for_model as class attribute")

        # 3. Instance Attribute Access (If class access failed)
        if not description and isinstance(tool_class_obj, type):
            try:
                logger.debug("Trying to instantiate class to get description")
                instance = tool_class_obj()
                if hasattr(instance, 'description'):
                    raw_value = getattr(instance, 'description')
                    logger.debug(f"Raw value from instance attribute 'description': type={type(raw_value)}, value='{str(raw_value)[:150]}...'")
                    if isinstance(raw_value, str):
                        description = raw_value
                        logger.debug("Using description on instance")
                elif hasattr(instance, 'description_for_model'):
                    raw_value = getattr(instance, 'description_for_model')
                    logger.debug(f"Raw value from instance attribute 'description_for_model': type={type(raw_value)}, value='{str(raw_value)[:150]}...'")
                    if isinstance(raw_value, str):
                        description = raw_value
                        logger.debug("Using description_for_model on instance")
            except Exception as e:
                logger.debug(f"Could not instantiate or get description from instance: {e}")

        # 4. Docstring Fallback
        if not description and hasattr(tool_class_obj, '__doc__') and tool_class_obj.__doc__:
            raw_value = tool_class_obj.__doc__
            logger.debug(f"Raw value from __doc__: type={type(raw_value)}, value='{str(raw_value)[:150]}...'")
            if isinstance(raw_value, str):
                description = raw_value
                logger.debug("Using docstring for description")

        # 5. Final check and cleaning
        if not description:
            logger.warning(f"No description found for {tool_class_name}")
            return f"Description not found for {tool_class_name}"

        if isinstance(description, str):
            # Clean multiline string indentation
            description = description.strip()
            if "\\n" in description:
                lines = description.split("\\n")
                if lines and not lines[0].strip() and len(lines) > 1:
                    lines = lines[1:]
                if len(lines) > 1:
                    non_empty = [line for line in lines if line.strip()]
                    if non_empty:
                        try:
                            indented_lines = [line for line in non_empty if line.lstrip() != line]
                            if indented_lines:
                                min_indent = min(len(line) - len(line.lstrip()) for line in indented_lines)
                            else:
                                min_indent = 0
                            cleaned_lines = []
                            for line in lines:
                                if len(line) >= min_indent and line[:min_indent].isspace():
                                     cleaned_lines.append(line[min_indent:])
                                else:
                                     cleaned_lines.append(line)
                            lines = cleaned_lines
                        except ValueError:
                            logger.warning(f"Could not determine indentation for {tool_class_name}")
                            pass
                description = "\\n".join(lines).strip()

            # ADDED: Targeted cleaning for the observed problematic format
            # If the description still contains the complex pattern, try to extract the core part
            if "Tool Name:" in description and "Tool Arguments:" in description and "Tool Description:" in description:
                logger.debug("Complex pattern detected, attempting targeted extraction.")
                try:
                    # Extract text after the LAST occurrence of "Tool Description:"
                    parts = description.rsplit("Tool Description:", 1)
                    if len(parts) > 1:
                        core_desc = parts[1].strip()
                        # Further clean up potential trailing parameter definitions
                        param_match = re.search(r'([a-z][a-z0-9_]*):\s*(?:\'[^\']*\'|\"[^\"]*\"|[^\s,]+)', core_desc)
                        if param_match:
                            if param_match.start() > 20: # Only if there is some text before the first param
                                core_desc = core_desc[:param_match.start()].strip()
                        
                        # Check if the extracted part is meaningful
                        if len(core_desc) > 10: # Avoid returning empty or very short strings
                             logger.debug(f"Extracted core description from complex pattern: {core_desc[:100]}...")
                             description = core_desc # Use the extracted part
                        else:
                            logger.warning("Extraction from complex pattern resulted in short/empty string, keeping original cleaned description.")
                    else:
                         logger.warning("Could not split complex pattern using 'Tool Description:'")
                except Exception as extract_err:
                    logger.error(f"Error during targeted extraction: {extract_err}")
            
            logger.debug(f"Final description: {description[:100]}...")
            return description
        else:
            logger.warning(f"Description for {tool_class_name} was not a string, converting.")
            return str(description).strip()

    except Exception as e:
        logger.error(f"Critical error in get_tool_description for {tool_class_name}: {e}", exc_info=True)
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