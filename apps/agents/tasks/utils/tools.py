import importlib
import logging
import sys
import functools
from crewai.tools import BaseTool as CrewAIBaseTool
from langchain.tools import BaseTool as LangChainBaseTool
from apps.agents.utils import get_tool_info
from pydantic import BaseModel
from typing import Any, Optional, Dict, List, Union, Callable, Type, Annotated

logger = logging.getLogger(__name__)

def load_tool_in_task(tool_model):
    """Load a tool from the database and return an instance ready for use with CrewAI.
    
    Since our BaseTool now inherits from CrewAI's BaseTool, we don't need any special adapters.
    """
    tool_info = get_tool_info(tool_model)
    
    try:
        print(f"Attempting to load tool: {tool_model.tool_class}.{tool_model.tool_subclass}", file=sys.stderr)
        logger.info(f"Attempting to load tool: {tool_model.tool_class}.{tool_model.tool_subclass}")
        
        module = importlib.import_module(tool_info['module_path'])
        tool_class = getattr(module, tool_info['class_name'])
        
        # Create the tool instance
        tool_instance = tool_class()
        
        # Special handling for known problematic tools
        if tool_model.tool_subclass == 'CodeInterpreterTool':
            # More robust error handling for CodeInterpreterTool
            logger.info("Adding enhanced error handling for CodeInterpreterTool")
            original_run = tool_instance._run
            
            def safe_run(*args, **kwargs):
                try:
                    # Handle the specific input pattern that causes errors
                    if len(args) > 0:
                        # Log the input for debugging
                        logger.debug(f"CodeInterpreterTool received: {str(args[0])[:100]}...")
                        
                        # Handle list input
                        if isinstance(args[0], list):
                            if len(args[0]) > 0 and isinstance(args[0][0], dict) and 'code' in args[0][0]:
                                code = args[0][0].get('code', '')
                                libraries = args[0][0].get('libraries_used', [])
                                return original_run(code=code, libraries_used=libraries)
                        
                        # Handle dictionary input
                        elif isinstance(args[0], dict) and 'code' in args[0]:
                            return original_run(code=args[0].get('code', ''), 
                                               libraries_used=args[0].get('libraries_used', []))
                    
                    # For other formats, pass through to the original method
                    return original_run(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in CodeInterpreterTool: {str(e)}", exc_info=True)
                    return f"Error executing code: {str(e)}"
            
            # Replace the _run method with our safe version
            tool_instance._run = safe_run
        
        # For Google tools, just make sure they have proper name and description
        # No need for special adapters anymore since our tools now inherit from CrewAI BaseTool
        if tool_model.tool_subclass in ['GenericGoogleAnalyticsTool', 'GenericGoogleSearchConsoleTool', 'GoogleAnalyticsTool', 'GoogleSearchConsoleTool', 'GoogleOverviewTool', 'GoogleReportTool', 'GoogleRankingsTool']:
            logger.info(f"Using Google tool: {tool_model.tool_subclass}")
            
            # Make sure name and description are set properly
            if not hasattr(tool_instance, 'name') or not tool_instance.name:
                tool_instance.name = tool_model.name
            if not hasattr(tool_instance, 'description') or not tool_instance.description:
                tool_instance.description = tool_model.description
                
        # Return the tool instance directly
        return tool_instance
        
    except Exception as e:
        logger.error(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", exc_info=True)
        print(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", file=sys.stderr)
        
        # Create a minimal fallback tool
        try:
            # Create a simple fallback tool that inherits from CrewAI BaseTool
            class FallbackTool(CrewAIBaseTool):
                name = tool_model.name
                description = f"Fallback for {tool_model.name} that returns an error message"
                
                def _run(self, *args, **kwargs):
                    return f"The tool {self.name} could not be loaded properly: {str(e)}"
            
            return FallbackTool()
        except Exception as fallback_error:
            logger.error(f"Failed to create fallback tool: {str(fallback_error)}", exc_info=True)
            return None 