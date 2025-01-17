import importlib
import logging
import sys
from crewai.tools import BaseTool as CrewAIBaseTool
from langchain.tools import BaseTool as LangChainBaseTool
from apps.agents.utils import get_tool_info

logger = logging.getLogger(__name__)

def load_tool_in_task(tool_model):
    tool_info = get_tool_info(tool_model)
    
    try:
        print(f"Attempting to load tool: {tool_model.tool_class}.{tool_model.tool_subclass}", file=sys.stderr)
        logger.info(f"Attempting to load tool: {tool_model.tool_class}.{tool_model.tool_subclass}")
        
        module = importlib.import_module(tool_info['module_path'])
        tool_class = getattr(module, tool_info['class_name'])
        
        if issubclass(tool_class, (CrewAIBaseTool, LangChainBaseTool)):
            tool_instance = tool_class()
            print(f"Tool loaded successfully: {tool_class.__name__}", file=sys.stderr)
            logger.info(f"Tool loaded successfully: {tool_class.__name__}")
            return tool_instance
        else:
            logger.error(f"Unsupported tool class: {tool_class}")
            return None
    except Exception as e:
        logger.error(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", exc_info=True)
        print(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", file=sys.stderr)
        return None 