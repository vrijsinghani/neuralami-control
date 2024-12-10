from apps.common.utils import get_llm, format_message
from apps.agents.utils import get_tool_classes
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory

from langchain.tools import Tool, StructuredTool

from apps.agents.chat.history import DjangoCacheMessageHistory
from channels.db import database_sync_to_async

import json
import logging
from apps.agents.chat.custom_agent import create_custom_agent
import re
from django.utils import timezone
from apps.seo_manager.models import Client
from langchain.schema import SystemMessage, AIMessage, HumanMessage

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, agent, model_name, client_data, callback_handler, session_id=None):
        self.agent = agent
        self.model_name = model_name
        self.client_id = client_data.get('client_id') if client_data else None
        self.callback_handler = callback_handler
        self.llm = None
        self.token_counter = None
        self.agent_executor = None
        self.processing = False
        self.session_id = session_id or f"{agent.id}_{self.client_id if self.client_id else 'no_client'}"

    async def initialize(self):
        """Initialize the chat service with LLM and agent"""
        try:
            # Get LLM and token counter from utils
            self.llm, self.token_counter = get_llm(
                model_name=self.model_name,
                temperature=0.0,
                streaming=True
            )

            # Load tools
            tools = await self._load_tools()
            
            # Initialize memory
            message_history = DjangoCacheMessageHistory(
                session_id=self.session_id,
                ttl=3600
            )

            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                chat_memory=message_history
            )

            # Generate system prompt once
            system_prompt = await self._create_agent_prompt()
            logger.debug(f"Generated system prompt: {system_prompt}")

            # Create the agent using the function
            agent = create_custom_agent(
                llm=self.llm,
                tools=tools,
                system_prompt=system_prompt  # Use the generated prompt
            )
            
            # Create agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=True,
                max_iterations=5,
                early_stopping_method="force",
                handle_parsing_errors=True,
                return_intermediate_steps=True
            )
            
            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str, is_edit: bool = False) -> str:
        """Process a message using the agent"""
        if not self.agent_executor:
            raise ValueError("Agent executor not initialized")

        if self.processing:
            return None

        try:
            self.processing = True
            
            # Store the user message first
            await database_sync_to_async(
                self.agent_executor.memory.chat_memory.add_message
            )(HumanMessage(content=message))
            
            # If this is an edited message, clear the memory
            if is_edit and self.agent_executor.memory:
                # Clear memory from the last user message onwards
                messages = self.agent_executor.memory.chat_memory.messages
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].type == 'human':
                        self.agent_executor.memory.chat_memory.messages = messages[:i]
                        break
            
            # Format input as expected by the agent
            input_data = {
                "input": message
            }
            
            logger.debug(f"Processing input: {input_data}")
            
            # Process message with streaming
            async for chunk in self.agent_executor.astream(
                input_data
            ):
                # Truncate the log output to first 250 chars
                log_chunk = str(chunk)[:250] + "..." if len(str(chunk)) > 250 else str(chunk)
                logger.debug(f"Raw chunk received: {log_chunk}")
                try:
                    # Handle different types of chunks
                    if isinstance(chunk, dict):
                        if "output" in chunk:
                            # Store AI response in memory
                            await database_sync_to_async(
                                self.agent_executor.memory.chat_memory.add_message
                            )(AIMessage(content=chunk["output"]))
                            # Send the actual output
                            await self.callback_handler.on_llm_new_token(chunk["output"])
                        elif "intermediate_steps" in chunk:
                            # Process tool steps
                            for step in chunk["intermediate_steps"]:
                                if len(step) >= 2:
                                    action, output = step
                                    if isinstance(output, str) and "Invalid or incomplete response" in output:
                                        continue
                                    
                                    if hasattr(action, 'tool') and action.tool != '_Exception':
                                        # Format tool interaction as structured system message
                                        tool_interaction = {
                                            'type': 'tool',
                                            'tool': action.tool,
                                            'input': action.tool_input,
                                            'output': str(output)
                                        }
                                        # Store tool interaction in memory
                                        await database_sync_to_async(
                                            self.agent_executor.memory.chat_memory.add_message
                                        )(SystemMessage(content=json.dumps(tool_interaction, indent=2)))
                                        
                                        # Send to websocket
                                        tool_msg = {
                                            'tool': action.tool,
                                            'input': action.tool_input,
                                            'output': output
                                        }
                                        await self.callback_handler.on_llm_new_token(tool_msg)
                        else:
                            # Store and send other content
                            content = str(chunk)
                            if content.strip() and "Invalid or incomplete response" not in content:
                                await database_sync_to_async(
                                    self.agent_executor.memory.chat_memory.add_message
                                )(AIMessage(content=content))
                                await self.callback_handler.on_llm_new_token(content)
                    else:
                        # Handle direct string output
                        content = str(chunk)
                        if content.strip() and "Invalid or incomplete response" not in content:
                            await database_sync_to_async(
                                self.agent_executor.memory.chat_memory.add_message
                            )(AIMessage(content=content))
                            await self.callback_handler.on_llm_new_token(content)
                            
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk: {str(chunk_error)}")
                    # Only send real errors, not parsing issues
                    if "Invalid or incomplete response" not in str(chunk_error):
                        await self.callback_handler.on_llm_new_token(f"Error processing response: {str(chunk_error)}")
                    continue
                    
            return None

        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            logger.error(error_msg)
            await self.callback_handler.on_llm_error(error_msg)
            raise
        finally:
            self.processing = False

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
        if self.client_id:
            try:
                # Fetch client data from database
                client = Client.objects.get(id=self.client_id)
                
                # Format business objectives from JSONField
                objectives_text = "\n".join([f"- {obj}" for obj in client.business_objectives]) if client.business_objectives else "No objectives set"

                client_context = f"""Current Context:
- Client ID: {client.id}
- Client Name: {client.name}
- Website URL: {client.website_url}
- Target Audience: {client.target_audience}
- Current Date: {timezone.now().strftime('%Y-%m-%d')}
- Business Objectives:
{objectives_text}"""
            except Client.DoesNotExist:
                client_context = f"""Current Context:
- Client ID: {self.client_id}
- Client Name: Not found
- Current Date: {timezone.now().strftime('%Y-%m-%d')}"""
        else:
            client_context = f"""Current Context:
- Client ID: N/A
- Current Date: {timezone.now().strftime('%Y-%m-%d')}"""

        logger.debug(f"role: {self.agent.role}, goal: {self.agent.goal}, backstory: {self.agent.backstory}")
        return f"""You are {self.agent.name}, an AI assistant.

Role: {self.agent.role}

Goal: {self.agent.goal if hasattr(self.agent, 'goal') else ''}

Backstory: {self.agent.backstory if hasattr(self.agent, 'backstory') else ''}

{client_context}
"""
