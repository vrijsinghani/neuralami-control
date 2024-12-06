import logging
from langchain_core.tools import Tool
from ..utils import get_tool_classes

logger = logging.getLogger(__name__)

class AgentToolManager:
    def __init__(self):
        pass

    async def load_tools(self, agent):
        """Load and initialize agent tools"""
        tools = []
        for tool_model in agent.tools.all():
            try:
                tool_classes = get_tool_classes(tool_model.tool_class)
                tool_class = next((cls for cls in tool_classes 
                                if cls.__name__ == tool_model.tool_subclass), None)
                
                if tool_class:
                    logger.info(f"Initializing tool: {tool_class.__name__}")
                    tool_instance = tool_class()
                    tools.append(tool_instance)
                else:
                    logger.error(f"Tool class not found: {tool_model.tool_subclass}")
            except Exception as e:
                logger.error(f"Error loading tool {tool_model.name}: {str(e)}")
        return tools

    def convert_to_langchain_tools(self, tools):
        """Convert custom tools to Langchain format"""
        return [self._create_langchain_tool(tool) for tool in tools]

    def _create_langchain_tool(self, tool):
        """Create individual Langchain tool"""
        formatted_name = ''.join(c for c in tool.name if c.isalnum() or c in '_-')[:64]
        
        async def tool_func(query: str, tool=tool):
            try:
                result = await self.execute_tool(tool, {"query": query})
                return result
            except Exception as e:
                logger.error(f"Tool execution error: {str(e)}")
                return f"Error: {str(e)}"

        return Tool(
            name=formatted_name,
            description=self._create_tool_description(tool),
            func=tool_func,
            coroutine=tool_func
        ) 