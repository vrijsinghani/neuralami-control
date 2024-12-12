from apps.common.utils import get_llm
from apps.agents.utils import get_tool_classes
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool, StructuredTool
from apps.agents.chat.history import DjangoCacheMessageHistory
from channels.db import database_sync_to_async
from apps.agents.chat.custom_agent import create_custom_agent
from apps.seo_manager.models import Client
from langchain.schema import SystemMessage, AIMessage, HumanMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
import json
import logging
from django.utils import timezone
from langchain.prompts import ChatPromptTemplate
from langchain.agents import create_structured_chat_agent

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, agent, model_name, client_data, callback_handler, session_id=None):
        self.agent = agent
        self.model_name = model_name
        self.client_data = client_data
        self.callback_handler = callback_handler
        self.llm = None
        self.token_counter = None
        self.agent_executor = None
        self.processing = False
        self.tool_cache = {}  # Add tool caching back
        self.session_id = session_id or f"{agent.id}_{client_data['client_id'] if client_data else 'no_client'}"
        self.message_history = None

    async def initialize(self):
        """Initialize the chat service with LLM and agent"""
        try:
            # Get LLM and token counter
            self.llm, self.token_counter = get_llm(
                model_name=self.model_name,
                temperature=0.7,
                streaming=True
            )

            # Initialize message history
            self.message_history = DjangoCacheMessageHistory(
                session_id=self.session_id,
                ttl=3600
            )

            # Initialize memory with message history
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                chat_memory=self.message_history,
                output_key="output",
                input_key="input"
            )

            # Load tools
            tools = await self._load_tools()
            
            # Get tool names and descriptions
            tool_names = [tool.name for tool in tools]
            tool_descriptions = [f"{tool.name}: {tool.description}" for tool in tools]

            # Create prompt with required variables
            prompt = ChatPromptTemplate.from_messages([
                ("system", """
{system_prompt}

You have access to the following tools:
{tools}

Tool Names: {tool_names}

IMPORTANT INSTRUCTIONS:
1. If a tool call fails, examine the error message and try to fix the parameters
2. If multiple tool calls fail, return a helpful message explaining the limitation
3. Always provide a clear response even if data is limited
4. Never give up without providing some useful information
5. Keep responses focused and concise

To use a tool, respond with:
{{"action": "tool_name", "action_input": {{"param1": "value1", "param2": "value2"}}}}

For final responses, use:
{{"action": "Final Answer", "action_input": "your response here"}}
"""),
                ("human", "{input}"),
                ("ai", "{agent_scratchpad}"),
                ("system", "Previous conversation:\n{chat_history}")
            ])

            # Create the agent
            agent = create_structured_chat_agent(
                llm=self.llm,
                tools=tools,
                prompt=prompt.partial(
                    system_prompt=await self._create_agent_prompt(),
                    tools="\n".join(tool_descriptions),
                    tool_names=", ".join(tool_names)
                )
            )
            
            # Create agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=True,
                max_iterations=10,
                max_execution_time=120,
                early_stopping_method="force",
                handle_parsing_errors=True,
                return_intermediate_steps=True,  # Enable to see tool usage
                output_key="output",
                input_key="input"
            )
            
            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Process a message using the agent"""
        if not self.agent_executor:
            raise ValueError("Agent executor not initialized")

        if self.processing:
            return None

        try:
            self.processing = True
            
            # Handle message editing
            if is_edit:
                await self._handle_message_edit()
            
            # Format input for agent
            input_data = {
                "input": message
            }
            
            error_count = 0
            last_error = None
            
            async for chunk in self.agent_executor.astream(
                input_data
            ):
                try:
                    if isinstance(chunk, dict):
                        if "output" in chunk:
                            await self.callback_handler.on_llm_new_token(chunk["output"])
                        elif "intermediate_steps" in chunk:
                            await self._process_tool_steps(chunk["intermediate_steps"])
                        else:
                            content = str(chunk)
                            if content.strip():
                                await self.callback_handler.on_llm_new_token(content)
                    else:
                        content = str(chunk)
                        if content.strip():
                            await self.callback_handler.on_llm_new_token(content)
                            
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk: {str(chunk_error)}")
                    error_count += 1
                    last_error = str(chunk_error)
                    if error_count >= 3:
                        await self.callback_handler.on_llm_new_token(
                            f"Multiple errors occurred. Last error: {last_error}"
                        )
                        return None
                    continue
                    
            return None

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await self.callback_handler.on_llm_error(str(e))
            raise
        finally:
            self.processing = False

    @database_sync_to_async
    def _handle_message_edit(self):
        """Clear history from last user message for edit handling"""
        messages = self.message_history.messages
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                self.message_history.messages = messages[:i]
                break

    async def _process_tool_steps(self, steps):
        """Process tool execution steps"""
        for step in steps:
            if len(step) >= 2:
                action, output = step
                if isinstance(output, str) and "Invalid or incomplete response" in output:
                    continue
                
                if hasattr(action, 'tool') and action.tool != '_Exception':
                    tool_interaction = {
                        'type': 'tool',
                        'tool': action.tool,
                        'input': action.tool_input,
                        'output': str(output)
                    }
                    
                    await self.callback_handler.on_llm_new_token({
                        'tool': action.tool,
                        'input': action.tool_input,
                        'output': output
                    })

    @database_sync_to_async
    def _load_tools(self):
        """Load and initialize agent tools asynchronously"""
        try:
            tools = []
            seen_tools = set()
            
            for tool_model in self.agent.tools.all():
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
                        
                        # Wrap tool output formatting
                        def format_tool_output(func):
                            def wrapper(*args, **kwargs):
                                result = func(*args, **kwargs)
                                if isinstance(result, dict):
                                    return json.dumps(result, indent=2)
                                return str(result)
                            return wrapper
                        
                        # Create structured or basic tool
                        if hasattr(tool_instance, 'args_schema'):
                            wrapped_run = format_tool_output(tool_instance._run)
                            tool = StructuredTool.from_function(
                                func=wrapped_run,
                                name=tool_model.name.lower().replace(" ", "_"),
                                description=self._create_tool_description(tool_instance, tool_model),
                                args_schema=tool_instance.args_schema,
                                coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None,
                                return_direct=False
                            )
                        else:
                            wrapped_run = format_tool_output(tool_instance._run)
                            tool = Tool(
                                name=tool_model.name.lower().replace(" ", "_"),
                                description=self._create_tool_description(tool_instance, tool_model),
                                func=wrapped_run,
                                coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None
                            )
                        
                        tools.append(tool)
                        logger.info(f"Successfully loaded tool: {tool_model.name}")
                        
                except Exception as e:
                    logger.error(f"Error loading tool {tool_model.name}: {str(e)}")
                    
            return tools
            
        except Exception as e:
            logger.error(f"Error loading tools: {str(e)}")
            return []

    def _create_tool_description(self, tool_instance, tool_model):
        """Create a detailed description for the tool"""
        try:
            base_description = tool_instance.description or tool_model.description
            schema = tool_instance.args_schema

            if schema:
                field_descriptions = []
                for field_name, field in schema.model_fields.items():
                    field_type = str(field.annotation).replace('typing.', '')
                    if hasattr(field.annotation, '__name__'):
                        field_type = field.annotation.__name__
                    
                    field_desc = field.description or ''
                    default = field.default
                    if default is Ellipsis:
                        default = "Required"
                    elif default is None:
                        default = "Optional"
                    
                    field_descriptions.append(
                        f"- {field_name} ({field_type}): {field_desc} Default: {default}"
                    )

                tool_description = f"""{base_description}

Parameters:
{chr(10).join(field_descriptions)}

Example:
{{"action": "{tool_model.name.lower().replace(' ', '_')}", 
  "action_input": {{
    "client_id": 123,
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "metrics": "newUsers",
    "dimensions": "date"
  }}
}}"""
                
                return tool_description
            
            return base_description

        except Exception as e:
            logger.error(f"Error creating tool description: {str(e)}")
            return base_description or "Tool description unavailable"

    @database_sync_to_async
    def _create_agent_prompt(self):
        """Create the system prompt for the agent"""
        client_context = ""
        
        if self.client_data:
            client_context = f"""Current Context:
- Client ID: {self.client_data.get('client_id', 'N/A')}
- Client Name: {self.client_data.get('client_name', 'N/A')}
- Website URL: {self.client_data.get('website_url', 'N/A')}
- Target Audience: {self.client_data.get('target_audience', 'N/A')}
- Current Date: {self.client_data.get('current_date', timezone.now().strftime('%Y-%m-%d'))}"""

            # Add business objectives if present
            objectives = self.client_data.get('business_objectives', [])
            if objectives:
                objectives_text = "\n".join([f"- {obj}" for obj in objectives])
                client_context += f"\n- Business Objectives:\n{objectives_text}"
        else:
            client_context = f"""Current Context:
- Current Date: {timezone.now().strftime('%Y-%m-%d')}"""

        return f"""You are {self.agent.name}, an AI assistant.

Role: {self.agent.role}

Goal: {self.agent.goal if hasattr(self.agent, 'goal') else ''}

Backstory: {self.agent.backstory if hasattr(self.agent, 'backstory') else ''}

{client_context}
"""
