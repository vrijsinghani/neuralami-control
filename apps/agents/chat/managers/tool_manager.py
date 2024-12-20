import logging
from typing import List, Dict, Any, Optional
from langchain.tools import Tool, StructuredTool
from apps.agents.utils import get_tool_classes
from channels.db import database_sync_to_async
from apps.agents.chat.formatters.tool_formatter import ToolFormatter

logger = logging.getLogger(__name__)

class ToolManager:
    """
    Manages tool loading, execution, and formatting.
    Consolidates tool-related functionality from across the codebase.
    """
    
    def __init__(self):
        """Initialize the ToolManager."""
        self.tools = []
        self.tool_formatter = ToolFormatter()

    async def load_tools(self, agent) -> List[Tool]:
        """Load and initialize agent tools."""
        try:
            tools = []
            seen_tools = set()
            
            # Get tools using database_sync_to_async
            agent_tools = await self._get_agent_tools(agent)
            
            for tool_model in agent_tools:
                try:
                    tool_key = f"{tool_model.tool_class}_{tool_model.tool_subclass}"
                    if tool_key in seen_tools:
                        continue
                    seen_tools.add(tool_key)

                    tool_classes = get_tool_classes(tool_model.tool_class)
                    tool_class = next((cls for cls in tool_classes 
                                   if cls.__name__ == tool_model.tool_subclass), None)
                    
                    if tool_class:
                        logger.info(f"Initializing tool: {tool_class.__name__}")
                        tool_instance = tool_class()
                        
                        # Convert to Langchain format
                        langchain_tool = self._create_langchain_tool(tool_instance)
                        if langchain_tool:
                            tools.append(langchain_tool)
                            
                except Exception as e:
                    logger.error(f"Error initializing tool {tool_model.tool_subclass}: {str(e)}")
                    continue

            self.tools = tools
            return tools
            
        except Exception as e:
            logger.error(f"Error loading tools: {str(e)}")
            raise

    @database_sync_to_async
    def _get_agent_tools(self, agent):
        """Get agent tools from database."""
        return list(agent.tools.all())

    def _create_langchain_tool(self, tool_instance) -> Optional[Tool]:
        """Create a Langchain tool from a tool instance."""
        try:
            # Use StructuredTool if args_schema is present
            if hasattr(tool_instance, 'args_schema'):
                return StructuredTool(
                    name=tool_instance.name,
                    description=self._create_tool_description(tool_instance),
                    func=tool_instance.run,
                    coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None,
                    args_schema=tool_instance.args_schema
                )
            else:
                return Tool(
                    name=tool_instance.name,
                    description=self._create_tool_description(tool_instance),
                    func=tool_instance.run,
                    coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None
                )
        except Exception as e:
            logger.error(f"Error creating Langchain tool: {str(e)}")
            return None

    def _create_tool_description(self, tool_instance) -> str:
        """Create a description for the tool."""
        description = tool_instance.description
        if hasattr(tool_instance, 'args_schema'):
            schema = tool_instance.args_schema.schema()
            if 'properties' in schema:
                args_desc = []
                for name, details in schema['properties'].items():
                    arg_desc = f"- {name}: {details.get('description', 'No description')}"
                    if details.get('type'):
                        arg_desc += f" (type: {details['type']})"
                    args_desc.append(arg_desc)
                if args_desc:
                    description += "\nArguments:\n" + "\n".join(args_desc)
        return description

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool with given arguments."""
        try:
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if not tool:
                raise ValueError(f"Tool not found: {tool_name}")
            
            if tool.coroutine:
                result = await tool.coroutine(**kwargs)
            else:
                result = tool.func(**kwargs)
                
            return result
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            raise

    def format_tool_output(self, content: Any) -> str:
        """Format tool output for display."""
        return self.tool_formatter.format_tool_output(content)

    def format_tool_usage(self, content: str, message_type: str = None) -> str:
        """Format tool usage messages."""
        return self.tool_formatter.format_tool_usage(content, message_type) 