from apps.common.utils import get_llm, format_message
from apps.agents.utils import get_tool_classes
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool, StructuredTool
from apps.agents.chat.history import DjangoCacheMessageHistory
from channels.db import database_sync_to_async
from langchain_core.messages import SystemMessage, HumanMessage
import json
import logging

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
        self.tool_cache = {}  # Cache for tool results
        self.session_id = session_id or f"{agent.id}_{client_data['client_id'] if client_data else 'no_client'}"

    async def initialize(self):
        """Initialize the chat service with LLM and agent"""
        try:
            # Get LLM and token counter from utils
            self.llm, self.token_counter = get_llm(
                model_name=self.model_name,
                temperature=0.7,
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
                chat_memory=message_history,
                output_key="output",
                input_key="input"
            )

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
            from langchain.agents import create_structured_chat_agent
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
                max_iterations=5,
                max_execution_time=60,
                early_stopping_method="force",
                handle_parsing_errors=True,
                return_intermediate_steps=False,
                output_key="output",
                input_key="input"
            )
            
            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str) -> str:
        """Process a message using the agent"""
        if not self.agent_executor:
            raise ValueError("Agent executor not initialized")

        if self.processing:
            return None

        try:
            self.processing = True
            
            # Format input as expected by the agent
            input_data = {
                "input": message,
                "chat_history": self.agent_executor.memory.chat_memory.messages if self.agent_executor.memory else []
            }
            
            logger.debug(f"Processing input: {input_data}")
            
            error_count = 0
            last_error = None
            
            # Process message with streaming
            async for chunk in self.agent_executor.astream(
                input_data
            ):
                logger.debug(f"Received chunk: {chunk}")
                try:
                    # Handle different types of chunks
                    if isinstance(chunk, dict):
                        if 'steps' in chunk:
                            for step in chunk['steps']:
                                if step.action.tool == '_Exception':
                                    error_count += 1
                                    last_error = step.log
                                    if error_count >= 3:
                                        # After 3 errors, try to salvage what we can
                                        error_summary = "I encountered some issues processing the data, but here's what I found:\n\n"
                                        if 'observation' in step:
                                            error_summary += f"- {step.observation}\n"
                                        if last_error:
                                            error_summary += f"\nDetails: {last_error}"
                                        await self.callback_handler.on_llm_new_token(error_summary)
                                        return None
                                    continue
                                
                        if "output" in chunk:
                            # Send the actual output
                            await self.callback_handler.on_llm_new_token(chunk["output"])
                        elif "intermediate_steps" in chunk:
                            # Log tool usage
                            for step in chunk["intermediate_steps"]:
                                if len(step) >= 2:
                                    action, output = step
                                    if not isinstance(output, str) and hasattr(output, '__str__'):
                                        output = str(output)
                                    tool_msg = f"Using tool: {action.tool}\nInput: {action.tool_input}\nOutput: {output}"
                                    await self.callback_handler.on_llm_new_token(tool_msg)
                        else:
                            # Send any other content
                            content = str(chunk)
                            if content.strip():  # Only send non-empty content
                                await self.callback_handler.on_llm_new_token(content)
                    else:
                        # Handle direct string output
                        content = str(chunk)
                        if content.strip():  # Only send non-empty content
                            await self.callback_handler.on_llm_new_token(content)
                            
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk: {str(chunk_error)}")
                    error_count += 1
                    last_error = str(chunk_error)
                    if error_count >= 3:
                        await self.callback_handler.on_llm_new_token(
                            f"Multiple errors occurred while processing the response. Last error: {last_error}"
                        )
                        return None
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
                        
                        # Wrap tool with caching
                        original_run = tool_instance._run
                        async def cached_run(*args, **kwargs):
                            cache_key = f"{tool_instance.__class__.__name__}:{json.dumps(kwargs, sort_keys=True)}"
                            if cache_key in self.tool_cache:
                                logger.info(f"Cache hit for tool: {cache_key}")
                                return self.tool_cache[cache_key]
                            
                            result = await original_run(*args, **kwargs)
                            self.tool_cache[cache_key] = result
                            return result
                            
                        tool_instance._run = cached_run
                        
                        # Create structured or basic tool
                        if hasattr(tool_instance, 'args_schema'):
                            tool = StructuredTool.from_function(
                                func=tool_instance._run,
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
                                func=tool_instance._run,
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
- Current Date: {self.client_data.get('current_date', 'N/A')}"""

        return f"""You are {self.agent.name}, an AI assistant.
Role: {self.agent.role}

{client_context}

{self.agent.use_system_prompt if self.agent.use_system_prompt else ''}

CRITICAL INSTRUCTIONS:
1. You MUST respond with ONLY a single JSON object in one of these two formats:

For using a tool:
{{"action": "tool_name", "action_input": {{"param1": "value1", "param2": "value2"}}}}

For final answers:
{{"action": "Final Answer", "action_input": "your response here"}}

2. When handling tool outputs:
   - If you receive a large amount of data, focus on relevant parts
   - Break down analysis into smaller steps if needed
   - If a tool returns HTML or complex data, extract key information first
   - Always provide a clear, structured response even with partial data

3. Error Handling:
   - If a tool call fails, try a different approach
   - If you can't parse all the data, focus on what you can understand
   - Never give up without providing some useful insights
   - If you hit multiple errors, summarize what you learned and suggest next steps

4. Response Format:
   - Keep responses focused and concise
   - Format data in tables when presenting multiple metrics
   - Use bullet points for lists
   - Include specific numbers and metrics when available

5. NEVER:
   - Return raw HTML or script tags in your response
   - Include multiple JSON objects in one response
   - Leave analysis incomplete without explanation
   - Exceed response length limits

Example Tool Usage:
{{"action": "scrape_website_content", "action_input": {{"website": "https://example.com", "output_type": "text"}}}}

Example Final Answer:
{{"action": "Final Answer", "action_input": "Based on the analysis:\\n- Website has proper meta tags\\n- Mobile responsiveness score: 95/100\\n- Found 3 broken links\\n\\nRecommendations:\\n1. Fix broken links\\n2. Add alt text to images\\n3. Improve page load speed"}}"""