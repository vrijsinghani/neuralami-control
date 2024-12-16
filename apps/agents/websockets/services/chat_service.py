from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool, StructuredTool, BaseTool
from langchain_core.messages import (
    BaseMessage,
    HumanMessage, 
    AIMessage,
    messages_from_dict,
    messages_to_dict
)
from apps.agents.chat.history import DjangoCacheMessageHistory
from channels.db import database_sync_to_async
from langchain.schema import SystemMessage
import json
import logging
from django.utils import timezone
from apps.common.utils import get_llm, tokenize
from apps.agents.utils import get_tool_classes
from apps.agents.chat.formatters import TableFormatter
from functools import lru_cache
from django.core.cache import cache
from typing import Optional, List, Any, Dict
import asyncio
from aiocache import cached
from aiocache.serializers import PickleSerializer
import tiktoken
from apps.seo_manager.models import Client
from django.db import models

logger = logging.getLogger(__name__)

class ChatServiceError(Exception):
    """Base exception for chat service errors"""
    pass

class ToolExecutionError(ChatServiceError):
    """Raised when a tool execution fails"""
    pass

class TokenLimitError(ChatServiceError):
    """Raised when token limit is exceeded"""
    pass

class ChatService:
    def __init__(self, agent, model_name, client_data, callback_handler, session_id=None):
        self.agent = agent
        self.model_name = model_name
        self.client_data = client_data
        self.callback_handler = callback_handler
        self.llm = None
        self.token_counter = None
        self.agent_executor = None
        self.session_id = session_id or f"{agent.id}_{client_data['client_id'] if client_data else 'no_client'}"
        self.message_history = DjangoCacheMessageHistory(
            session_id=self.session_id,
            agent_id=agent.id
        )
        self.processing_lock = asyncio.Lock()
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.max_token_limit = 64000  # Adjust based on model

    async def initialize(self) -> Optional[AgentExecutor]:
        """Initialize the chat service with LLM and agent"""
        try:
            # Validate client_id if present
            if self.client_data and self.client_data.get('client_id'):
                from apps.seo_manager.models import Client
                try:
                    client = await database_sync_to_async(Client.objects.get)(id=self.client_data['client_id'])
                    #logger.info(f"Initialized chat service for client: {client.id} ({client.name})")
                except Client.DoesNotExist:
                    logger.error(f"Client not found with ID: {self.client_data['client_id']}")
                    raise ValueError(f"Client not found with ID: {self.client_data['client_id']}")

            # Get LLM and token counter
            self.llm, self.token_counter = get_llm(
                model_name=self.model_name,
                temperature=0.7,
                streaming=True
            )
            
            # Add token counter to callbacks
            self.llm.callbacks = [self.token_counter]

            # Initialize memory with token counting wrapper
            memory = self._create_token_aware_memory()

            # Load tools
            tools = await self._load_tools()

            # Get tool names and descriptions
            tool_names = [tool.name for tool in tools]
            tool_descriptions = [f"{tool.name}: {tool.description}" for tool in tools]

            # Get chat history for prompt
            chat_history = await self.message_history.aget_messages()
            
            # Create prompt template
            prompt = ChatPromptTemplate.from_messages([
                ("system", f"""{{system_prompt}}

Previous conversation:
{{chat_history}}

Respond to the human as helpfully and accurately as possible. You have access to the following tools:
{{tools}}

Valid "action" values: "Final Answer" or {{tool_names}}
Provide only ONE action per $JSON_BLOB, as shown:
```
{{{{
  "action": $TOOL_NAME,
  "action_input": $INPUT
}}}}
```
Follow this format:
Question: input question to answer
Thought: consider previous and subsequent steps
Action:
```
$JSON_BLOB
```
Observation: action result
... (repeat Thought/Action/Observation N times)
Thought: I know what to respond
Action:
```
{{{{
  "action": "Final Answer",
  "action_input": "Final response to human"
}}}}
Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation

IMPORTANT: When you receive a tool response containing an "error" field:
1. Read the error message and suggestion carefully
2. If it's a validation error, fix the parameter format according to correct_format
3. Retry the tool call with corrected parameters
4. If you fail after 2 retries, explain the issue and try a different approach

Example error response in json format:
{{{{
    "error": "validation_error",
    "message": "Invalid date format",
    "correct_format": {{{{"start_date": "YYYY-MM-DD"}}}},
    "suggestion": "Please use YYYY-MM-DD format"
}}}}
Begin!
"""),
                ("human", "{input}"),
                ("ai", "{agent_scratchpad}")
            ])

            # Prepare prompt
            prompt = prompt.partial(
                system_prompt=await self._create_agent_prompt(),
                tools="\n".join(tool_descriptions),
                tool_names=", ".join(tool_names),
                chat_history=str(chat_history)
            )

            # Create the agent
            agent = create_structured_chat_agent(
                llm=self.llm,
                prompt=prompt,
                tools=tools
            )

            # Create the agent executor with token counter
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=False,
                max_iterations=25,
                early_stopping_method="force",
                handle_parsing_errors=True,
                return_intermediate_steps=True,
                handle_tool_errors=True,
                output_key="output",
                input_key="input",
                callbacks=[self.token_counter]  # Add token counter to executor callbacks
            )

            # Reset session token totals
            await self._reset_session_token_totals()

            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise

    def _create_token_aware_memory(self) -> ConversationBufferMemory:
        """Create memory with token limit enforcement"""
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            chat_memory=self.message_history,
            output_key="output",
            input_key="input"
        )

        # Wrap the add_message methods to check token counts
        original_add_message = self.message_history.add_message

        async def check_token_limit(message: str) -> None:
            """Async token limit checker"""
            try:
                messages = await self.message_history.aget_messages()
                total_tokens = sum(
                    tokenize(str(msg.content), self.tokenizer) 
                    for msg in messages
                )
                new_tokens = tokenize(message, self.tokenizer)
                
                if total_tokens + new_tokens > self.max_token_limit:
                    # Remove oldest messages until we have space
                    while total_tokens + new_tokens > self.max_token_limit and messages:
                        removed_msg = messages.pop(0)
                        total_tokens -= tokenize(str(removed_msg.content), self.tokenizer)
                    
                    # Update cache with remaining messages
                    messages_dict = messages_to_dict(messages)
                    cache.set(self.message_history.key, messages_dict, self.message_history.ttl)

            except Exception as e:
                logger.error(f"Error checking token limit: {str(e)}")
                raise

        async def wrapped_add_message(message: BaseMessage, **kwargs) -> None:
            """Async wrapper for add_message that handles token usage"""
            try:
                await check_token_limit(str(message.content))
                # Pass through any additional kwargs (including token_usage)
                await original_add_message(message, **kwargs)
            except Exception as e:
                logger.error(f"Error in wrapped_add_message: {str(e)}")
                raise

        # Replace the add_message method with our wrapped version
        self.message_history.add_message = wrapped_add_message

        return memory

    @database_sync_to_async
    def _create_agent_prompt(self):
        """Create the system prompt for the agent"""
        try:
            client_context = ""
            
            if self.client_data and self.client_data.get('client_id'):
                # Get client synchronously since we're already in a sync context due to decorator
                client = Client.objects.select_related().get(id=self.client_data['client_id'])
                
                client_context = f"""Current Context:
- Client ID: {client.id}
- Client Name: {client.name}
- Website URL: {client.website_url}
- Target Audience: {client.target_audience or 'N/A'}
- Current Date: {timezone.now().strftime('%Y-%m-%d')}

IMPORTANT: When using tools that require client_id, always use {client.id} as the client_id parameter.
"""

                # Add business objectives if present
                if client.business_objectives:
                    objectives_text = "\n".join([f"- {obj}" for obj in client.business_objectives])
                    client_context += f"\n\nBusiness Objectives:\n{objectives_text}"

                # Add client profile if available
                if client.client_profile:
                    client_context += f"\n\nClient Profile:\n{client.client_profile}"

            else:
                client_context = f"""Current Context:
- Current Date: {timezone.now().strftime('%Y-%m-%d')}"""
                
            logger.debug("\n"+self._create_box(client_context, "🔍 CLIENT CONTEXT"))

            return f"""You are {self.agent.name}, an AI assistant.

Role: {self.agent.role}

Goal: {self.agent.goal if hasattr(self.agent, 'goal') else ''}

Backstory: {self.agent.backstory if hasattr(self.agent, 'backstory') else ''}

{client_context}
"""
        except Client.DoesNotExist:
            logger.error(f"Client not found with ID: {self.client_data.get('client_id')}")
            return self._create_default_prompt()
        except Exception as e:
            logger.error(f"Error creating agent prompt: {str(e)}", exc_info=True)
            return self._create_default_prompt()

    def _create_box(self, content: str, title: str = "", width: int = 80) -> str:
        """Create a pretty ASCII box with content"""
        lines = []
        
        # Top border with title
        if title:
            title = f" {title} "
            padding = (width - len(title)) // 2
            lines.append("╔" + "═" * padding + title + "═" * (width - padding - len(title)) + "╗")
        else:
            lines.append("╔" + "═" * width + "╗")
            
        # Content
        for line in content.split('\n'):
            # Split long lines
            while len(line) > width:
                split_at = line[:width].rfind(' ')
                if split_at == -1:
                    split_at = width
                lines.append("║ " + line[:split_at].ljust(width-2) + " ║")
                line = line[split_at:].lstrip()
            lines.append("║ " + line.ljust(width-2) + " ║")
            
        # Bottom border
        lines.append("╚" + "═" * width + "╝")
        
        return "\n".join(lines)

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Process a message using the agent"""
        async with self.processing_lock:
            try:
                # Reset token counter for this message
                if hasattr(self, 'token_counter'):
                    self.token_counter.input_tokens = 0
                    self.token_counter.output_tokens = 0

                # Log user input
                logger.info("\n" + self._create_box(
                    f"Message: {message}\n"
                    f"Is Edit: {is_edit}",
                    "📝 USER INPUT"
                ))

                await self._safely_add_message(message, is_user=True)

                if is_edit:
                    await self._handle_message_edit()

                try:
                    # Log start of agent execution
                    logger.info("\n" + self._create_box(
                        f"Starting agent execution for message: {message[:100]}...",
                        "🚀 AGENT EXECUTION START"
                    ))

                    response = await self.agent_executor.ainvoke({
                        "input": message,
                        "chat_history": await self.message_history.aget_messages()
                    })

                    final_response = await self._format_response(response)
                    
                    # Get conversation token usage
                    conv_tokens = await self._get_conversation_token_usage()
                    
                    # Create token usage dict from counter
                    current_usage = {
                        'prompt_tokens': self.token_counter.input_tokens,
                        'completion_tokens': self.token_counter.output_tokens,
                        'total_tokens': self.token_counter.input_tokens + self.token_counter.output_tokens,
                        'model': self.model_name
                    }

                    # Log final response with token usage
                    logger.info("\n" + self._create_box(
                        f"Response: {final_response}\n"
                        f"\nToken Usage This Response:\n"
                        f"  Prompt Tokens: {current_usage['prompt_tokens']:,}\n"
                        f"  Completion Tokens: {current_usage['completion_tokens']:,}\n"
                        f"  Total Tokens: {current_usage['total_tokens']:,}\n"
                        f"  Model: {current_usage['model']}\n"
                        f"\nConversation Totals:\n"
                        f"  Total Prompt Tokens: {conv_tokens.get('prompt_tokens', 0):,}\n"
                        f"  Total Completion Tokens: {conv_tokens.get('completion_tokens', 0):,}\n"
                        f"  Total Tokens: {conv_tokens.get('total_tokens', 0):,}",
                        "🎯 FINAL ANSWER WITH TOKEN USAGE"
                    ))

                    # Store token usage
                    await self.message_history.add_message(
                        AIMessage(content=final_response),
                        token_usage=current_usage
                    )

                    # Reset token counter after storing usage
                    if hasattr(self, 'token_counter'):
                        self.token_counter.input_tokens = 0
                        self.token_counter.output_tokens = 0

                    await self._handle_response(final_response)

                except Exception as e:
                    logger.error("\n" + self._create_box(str(e), "❌ ERROR"))
                    raise

            except Exception as e:
                logger.error(f"Critical error: {str(e)}", exc_info=True)
                await self.callback_handler.on_llm_error("A critical error occurred")
                return None

    async def _safely_add_message(self, message: str, is_user: bool = True) -> None:
        """Safely add message to history"""
        try:
            if is_user:
                msg = HumanMessage(content=message)
            else:
                msg = AIMessage(content=message)
                
            await self.message_history.add_message(msg)
            
        except Exception as e:
            logger.error(f"Error adding message to history: {str(e)}", exc_info=True)
            raise ChatServiceError("Failed to store message in history")

    async def _format_response(self, response: dict) -> str:
        """Format agent response"""
        try:
            #logger.debug(f"Response: {response}")
            
            output = response.get("output")
            if not output:
                return "No response generated"
                
            # If output is a dict, check for tabular data
            if isinstance(output, dict):
                if "formatted_table" in output:
                    return output["formatted_table"]
                if TableFormatter.detect_tabular_data(output):
                    return TableFormatter.format_table(output)
                return json.dumps(output, indent=2)
                
            # If output is a string but contains JSON, try to parse and format
            if isinstance(output, str) and (output.startswith('{') or output.startswith('[')):
                try:
                    json_data = json.loads(output)
                    if "formatted_table" in json_data:
                        return json_data["formatted_table"]
                    if TableFormatter.detect_tabular_data(json_data):
                        return TableFormatter.format_table(json_data)
                    return json.dumps(json_data, indent=2)
                except json.JSONDecodeError:
                    pass
                    
            return output

        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}", exc_info=True)
            return "Error formatting response"

    async def _handle_response(self, response: str) -> None:
        """Handle successful response"""
        try:
            #logger.debug(f"Final response: {response}")
            await self.callback_handler.on_llm_new_token(response)
            await self._safely_add_message(response, is_user=False)
        except Exception as e:
            logger.error(f"Error handling response: {str(e)}", exc_info=True)
            raise ChatServiceError("Failed to handle response")

    async def _handle_error(self, error_msg: str, exception: Exception, unexpected: bool = False) -> None:
        """Handle errors consistently"""
        await self.callback_handler.on_llm_error(error_msg)
        if unexpected:
            logger.error(f"Unexpected error: {str(exception)}", exc_info=True)
            raise ChatServiceError(str(exception))
        else:
            logger.warning(f"Known error: {str(exception)}")
            raise exception

    @database_sync_to_async
    def _load_tools(self) -> List[BaseTool]:
        """Load and initialize agent tools"""
        try:
            tools = []
            seen_tools = set()
            
            for tool_model in self.agent.tools.all():
                try:
                    tool_key = f"{tool_model.tool_class}_{tool_model.tool_subclass}"
                    if tool_key in seen_tools:
                        continue
                    seen_tools.add(tool_key)

                    # Get tool classes directly from the module path
                    tool_classes = get_tool_classes(tool_model.tool_class)
                    tool_class = next((cls for cls in tool_classes 
                                   if cls.__name__ == tool_model.tool_subclass), None)
                    
                    if tool_class:
                        logger.info(f"Initializing tool: {tool_class.__name__}")
                        tool_instance = tool_class()
                        
                        # Wrap tool output formatting
                        wrapped_run = self._wrap_tool_output(tool_instance._run)
                        
                        # Create structured or basic tool
                        if hasattr(tool_instance, 'args_schema'):
                            tool = StructuredTool.from_function(
                                func=wrapped_run,
                                name=tool_model.name.lower().replace(" ", "_"),
                                description=self._create_tool_description(tool_instance, tool_model),
                                args_schema=tool_instance.args_schema,
                                coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None,
                                return_direct=False
                            )
                        else:
                            tool = Tool(
                                name=tool_model.name.lower().replace(" ", "_"),
                                description=self._create_tool_description(tool_instance, tool_model),
                                func=wrapped_run,
                                coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None
                            )
                        
                        tools.append(tool)
                        #logger.info(f"Successfully loaded tool: {tool_model.name}")
                        
                except Exception as e:
                    logger.error(f"Error loading tool {tool_model.name}: {str(e)}")
                    continue
                    
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

                # Add example with actual client ID
                tool_description = f"""{base_description}

Parameters:
{chr(10).join(field_descriptions)}

Example:
{{"action": "{tool_model.name.lower().replace(' ', '_')}", 
  "action_input": {{
    "client_id": {self.client_data.get('client_id', 123) if self.client_data else 123},
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

    def _wrap_tool_output(self, func):
        """Wrap synchronous tool output with token tracking"""
        def wrapper(*args, **kwargs):
            try:
                # Log tool execution start
                logger.info("\n" + self._create_box(
                    f"Tool: {func.__name__}\n"
                    f"Args: {args}\n"
                    f"Kwargs: {kwargs}",
                    "🔧 TOOL EXECUTION START"
                ))
                
                result = func(*args, **kwargs)
                
                # Track token usage if available
                token_usage = None
                if isinstance(result, dict) and 'token_usage' in result:
                    token_usage = result.pop('token_usage')
                    # Instead of trying to track directly, add to token counter
                    if hasattr(self, 'token_counter'):
                        self.token_counter.input_tokens += token_usage.get('prompt_tokens', 0)
                        self.token_counter.output_tokens += token_usage.get('completion_tokens', 0)
                
                formatted = self._format_tool_result(result)
                
                # Log tool execution result
                logger.info("\n" + self._create_box(
                    f"Tool: {func.__name__}\n"
                    f"Result: {formatted[:500]}{'...' if len(formatted) > 500 else ''}\n"
                    + (f"\nToken Usage:\n"
                       f"  Prompt Tokens: {token_usage.get('prompt_tokens', 0):,}\n"
                       f"  Completion Tokens: {token_usage.get('completion_tokens', 0):,}\n"
                       f"  Total Tokens: {token_usage.get('total_tokens', 0):,}"
                       if token_usage else ""),
                    "📊 TOOL EXECUTION COMPLETE"
                ))
                
                return formatted

            except Exception as e:
                error_msg = str(e)
                logger.error("\n" + self._create_box(
                    f"Tool: {func.__name__}\n"
                    f"Error: {error_msg}\n"
                    f"Args: {args}\n"
                    f"Kwargs: {kwargs}",
                    "❌ TOOL EXECUTION ERROR"
                ))
                
                if "validation error" in error_msg.lower():
                    return json.dumps({
                        "error": "validation_error",
                        "message": error_msg,
                        "tool": func.__name__,
                        "args": args,
                        "kwargs": kwargs
                    })
                
                return json.dumps({
                    "error": "tool_error",
                    "message": error_msg,
                    "tool": func.__name__,
                    "args": args,
                    "kwargs": kwargs
                })
        return wrapper

    def _wrap_async_tool_output(self, func):
        """Wrap asynchronous tool output with validation error handling"""
        async def wrapper(*args, **kwargs):
            try:
                # Log tool execution in a box
                logger.info("\n" + self._create_box(
                    f"Tool: {func.__name__}\nArgs: {args}\nKwargs: {kwargs}", 
                    "🔧 TOOL EXECUTION"
                ))
                
                result = await func(*args, **kwargs)
                formatted = self._format_tool_result(result)
                
                # Log tool result in a box
                logger.info("\n" + self._create_box(
                    formatted[:500] + "..." if len(formatted) > 500 else formatted,
                    "📊 TOOL RESULT"
                ))
                
                return formatted

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Tool execution failed: {error_msg}", exc_info=True)
                
                # Format validation errors specially
                if "validation error" in error_msg.lower():
                    return json.dumps({
                        "error": "validation_error",
                        "message": error_msg,
                        "tool": func.__name__,
                        "args": args,
                        "kwargs": kwargs
                    })
                
                # Return other errors
                return json.dumps({
                    "error": "tool_error",
                    "message": error_msg,
                    "tool": func.__name__,
                    "args": args,
                    "kwargs": kwargs
                })
        return wrapper

    def _format_tool_result(self, result: Any) -> str:
        """Format tool output consistently"""
        try:
            if isinstance(result, dict):
                # If result contains tabular data, format it
                if TableFormatter.detect_tabular_data(result):
                    formatted = TableFormatter.format_table(result)
                    # Return the raw data as well for the agent to analyze
                    return json.dumps({
                        "formatted_table": formatted,
                        "raw_data": result
                    }, indent=2)
                return json.dumps(result, indent=2)
            return str(result)
        except Exception as e:
            logger.error(f"Error formatting tool result: {str(e)}")
            return str(result)

    @database_sync_to_async
    def _handle_message_edit(self) -> None:
        """Handle message editing with thread safety"""
        try:
            messages = self.message_history.messages.copy()  # Create a copy for thread safety
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    self.message_history.messages = messages[:i]
                    break
        except Exception as e:
            logger.error(f"Error handling message edit: {str(e)}")
            raise ChatServiceError("Failed to edit message history")

    async def _track_tool_token_usage(self, token_usage: Dict, tool_name: str):
        """Track token usage for tool execution"""
        if not hasattr(self.message_history, 'conversation_id'):
            return
        
        try:
            await database_sync_to_async(TokenUsage.objects.create)(
                conversation_id=self.message_history.conversation_id,
                prompt_tokens=token_usage.get('prompt_tokens', 0),
                completion_tokens=token_usage.get('completion_tokens', 0),
                total_tokens=token_usage.get('total_tokens', 0),
                model=token_usage.get('model', ''),
                metadata={
                    'tool_name': tool_name,
                    'type': 'tool_execution'
                }
            )
        except Exception as e:
            logger.error(f"Error tracking tool token usage: {str(e)}")

    async def _get_conversation_token_usage(self) -> Dict:
        """Get total token usage for the conversation"""
        if not hasattr(self.message_history, 'conversation_id'):
            return {}
        
        try:
            from apps.agents.models import TokenUsage
            
            # Get stored token usage from database
            stored_usage = await database_sync_to_async(TokenUsage.objects.filter(
                conversation_id=self.message_history.conversation_id
            ).aggregate)(
                total_prompt_tokens=models.Sum('prompt_tokens'),
                total_completion_tokens=models.Sum('completion_tokens'),
                total_tokens=models.Sum('total_tokens')
            )
            
            # Get current session's tokens
            current_prompt_tokens = getattr(self.token_counter, 'input_tokens', 0)
            current_completion_tokens = getattr(self.token_counter, 'output_tokens', 0)
            
            # Cache key for storing running totals for this session
            session_cache_key = f"token_totals_{self.message_history.session_id}"
            
            # Get or initialize session running totals
            session_totals = cache.get(session_cache_key, {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            })
            
            # Add current tokens to session totals
            session_totals['prompt_tokens'] += current_prompt_tokens
            session_totals['completion_tokens'] += current_completion_tokens
            session_totals['total_tokens'] += (current_prompt_tokens + current_completion_tokens)
            
            # Store updated session totals
            cache.set(session_cache_key, session_totals, 3600)  # 1 hour expiry
            
            # Combine database totals with session totals
            return {
                'prompt_tokens': (stored_usage['total_prompt_tokens'] or 0) + session_totals['prompt_tokens'],
                'completion_tokens': (stored_usage['total_completion_tokens'] or 0) + session_totals['completion_tokens'],
                'total_tokens': (stored_usage['total_tokens'] or 0) + session_totals['total_tokens']
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation token usage: {str(e)}")
            return {}

    # Add a method to reset session token totals
    async def _reset_session_token_totals(self):
        """Reset token totals for the current session"""
        if hasattr(self.message_history, 'session_id'):
            session_cache_key = f"token_totals_{self.message_history.session_id}"
            cache.delete(session_cache_key)