import importlib
import logging
import sys
import functools
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
            
            # Wrap all tools with error resilient invoke method
            original_invoke = tool_instance.invoke
            
            @functools.wraps(original_invoke)
            def safe_invoke(input=None, **kwargs):
                try:
                    # Standard tool execution
                    return original_invoke(input=input, **kwargs)
                except Exception as e:
                    # Log the error but return a structured error response
                    logger.error(f"Error invoking tool {tool_instance.name}: {str(e)}", exc_info=True)
                    error_msg = f"Error using {tool_instance.name}: {str(e)}"
                    
                    # Return a properly structured error response that won't cause subscript errors
                    return error_msg
            
            # Apply the wrapper
            tool_instance.invoke = safe_invoke
            
            return tool_instance
        else:
            logger.error(f"Unsupported tool class: {tool_class}")
            return None
    except Exception as e:
        logger.error(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", exc_info=True)
        print(f"Error loading tool {tool_model.tool_class}.{tool_model.tool_subclass}: {str(e)}", file=sys.stderr)
        return None 