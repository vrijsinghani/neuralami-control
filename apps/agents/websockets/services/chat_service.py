from apps.common.utils import get_llm
from apps.agents.utils import get_tool_classes
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool, StructuredTool
from apps.agents.chat.history import DjangoCacheMessageHistory
from channels.db import database_sync_to_async
from langchain.schema import SystemMessage, AIMessage, HumanMessage
import json
import logging
from django.utils import timezone
from langchain.prompts import ChatPromptTemplate
from langchain.agents.output_parsers import JSONAgentOutputParser
from langgraph.graph import StateGraph
from typing import TypedDict, List, Dict, Any
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain_core.agents import AgentFinish, AgentAction

logger = logging.getLogger(__name__)

class GraphState(TypedDict):
    messages: List[Dict]  # Chat history
    agent_outcome: Any    # Output of the agent (action or final answer)
    input: str           # User input
    intermediate_steps: List[Any]  # Tool usage and actions
    llm: Any  # LLM instance
    tools: List[Any]  # Available tools
    agent: Any  # Agent instance
    client_data: Dict  # Client context data

class ChatService:
    def __init__(self, agent, model_name, client_data, callback_handler, session_id=None):
        self.agent = agent
        self.model_name = model_name
        self.client_data = client_data
        self.callback_handler = callback_handler
        self.llm = None
        self.token_counter = None
        self.langraph = None
        self.processing = False
        self.tool_cache = {}
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

            # Create and store LangGraph instance
            self.langraph = await self._create_langraph(tools)

            return self.langraph

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise

    async def _create_langraph(self, tools):
        """Create the LangGraph instance"""
        graph = StateGraph(GraphState)

        # Add nodes
        graph.add_node("call_llm", self._call_llm_node)
        graph.add_node("tool_call", self._tool_call_node)
        graph.add_node("should_continue", self._should_continue_node)
        graph.add_node("final_response", self._final_response_node)

        # Add edges
        graph.add_edge("call_llm", "should_continue")
        graph.add_conditional_edges(
            "should_continue",
            lambda x: x["continue"],
            {
                "tool_call": "tool_call",
                "final_response": "final_response"
            }
        )
        graph.add_edge("tool_call", "call_llm")

        # Set entry point
        graph.set_entry_point("call_llm")

        return graph.compile()

    async def _call_llm_node(self, state):
        """Node to call the LLM with the current state."""
        messages = state["messages"]
        llm = state["llm"]
        tools = state["tools"]
        intermediate_steps = state.get("intermediate_steps", [])

        try:
            # If we have intermediate steps, check if we need to format the last result
            if intermediate_steps:
                last_step = intermediate_steps[-1]
                if isinstance(last_step, tuple) and len(last_step) == 2:
                    action, output = last_step
                    # Format the output for analysis
                    if isinstance(output, str):
                        try:
                            output_data = json.loads(output)
                            if isinstance(output_data, dict) and 'analytics_data' in output_data:
                                # Format analytics data for human reading
                                analytics_data = output_data['analytics_data']
                                formatted_response = "Here's the analysis of new users over the past 7 days:\n\n"
                                formatted_response += "Date | New Users\n"
                                formatted_response += "-|-\n"
                                for day in analytics_data:
                                    formatted_response += f"{day['date']} | {int(day['newUsers'])}\n"
                                
                                return {
                                    "agent_outcome": AgentFinish(
                                        return_values={"output": formatted_response},
                                        log=str(output_data)
                                    )
                                }
                        except json.JSONDecodeError:
                            pass

            # Get tool names and descriptions
            tool_names = [tool.name for tool in tools]
            tool_descriptions = [f"{tool.name}: {tool.description}" for tool in tools]

            # Create prompt
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
6. For conversational messages that don't require tools, respond with:
{{"action": "Final Answer", "action_input": "your conversational response here"}}

To use a tool, respond with:
{{"action": "tool_name", "action_input": {{"param1": "value1", "param2": "value2"}}}}
"""),
                ("human", "{input}"),
                ("ai", "{agent_scratchpad}"),
                ("system", "Previous conversation:\n{chat_history}")
            ])

            # Prepare prompt
            prompt = prompt.partial(
                system_prompt=await self._create_agent_prompt(),
                tools="\n".join(tool_descriptions),
                tool_names=", ".join(tool_names)
            )

            # Create runnable
            runnable = prompt | llm | JSONAgentOutputParser()

            # Format intermediate steps for scratchpad
            scratchpad = format_to_openai_function_messages(intermediate_steps)
            
            # Call LLM
            response = await runnable.ainvoke({
                "input": state["input"],
                "agent_scratchpad": scratchpad,
                "chat_history": messages
            })

            logger.debug(f"LLM Response: {response}")

            # Handle response based on its type
            if isinstance(response, AgentFinish):
                return {
                    "agent_outcome": response
                }
            elif isinstance(response, AgentAction):
                return {
                    "agent_outcome": response
                }
            elif isinstance(response, dict):
                action = response.get("action")
                action_input = response.get("action_input")

                if action == "Final Answer":
                    return {
                        "agent_outcome": AgentFinish(
                            return_values={"output": action_input},
                            log=str(action_input)
                        )
                    }
                else:
                    # Convert dictionary to AgentAction
                    return {
                        "agent_outcome": AgentAction(
                            tool=action,
                            tool_input=action_input,
                            log=str(response)
                        )
                    }
            
            # If we get here, something unexpected happened
            error_msg = f"Unexpected LLM response type: {type(response)}"
            logger.error(error_msg)
            return {
                "agent_outcome": AgentFinish(
                    return_values={"output": error_msg},
                    log=error_msg
                )
            }

        except Exception as e:
            error_msg = f"Error in LLM node: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "agent_outcome": AgentFinish(
                    return_values={"output": error_msg},
                    log=error_msg
                )
            }

    async def _tool_call_node(self, state):
        """Node to handle tool calls."""
        agent_outcome = state.get("agent_outcome")
        tools = state.get("tools", [])

        logger.debug(f"Tool call node - agent_outcome type: {type(agent_outcome)}")
        logger.debug(f"Tool call node - agent_outcome: {agent_outcome}")

        # Handle AgentFinish
        if isinstance(agent_outcome, AgentFinish):
            return {
                "agent_outcome": agent_outcome,
                "continue": "final_response"
            }

        # Handle AgentAction
        if isinstance(agent_outcome, AgentAction):
            tool_name = agent_outcome.tool
            tool_input = agent_outcome.tool_input
            
            # Find the correct tool
            tool = next((tool for tool in tools if tool.name.lower().replace(" ", "_") == tool_name), None)

            if not tool:
                error_msg = f"Error: tool {tool_name} not found."
                logger.error(error_msg)
                return {
                    "agent_outcome": AgentFinish(
                        return_values={"output": error_msg},
                        log=error_msg
                    ),
                    "continue": "final_response"
                }

            # Execute the tool
            try:
                logger.debug(f"Executing tool {tool_name} with input {tool_input}")
                
                # Send tool start message
                await self.callback_handler.on_llm_new_token({
                    'message_type': 'tool_start',
                    'message': {
                        'name': tool_name,
                        'input': tool_input
                    }
                })
                
                # Handle async and sync tool execution
                if hasattr(tool, 'arun'):
                    output = await tool.arun(tool_input)
                elif hasattr(tool, '_arun'):
                    output = await tool._arun(tool_input)
                else:
                    output = await database_sync_to_async(tool.run)(tool_input)

                logger.debug(f"Tool execution successful: {output}")

                # Send tool output message
                await self.callback_handler.on_llm_new_token({
                    'message_type': 'tool_output',
                    'message': output
                })

                # Format the output for the agent's next step
                return {
                    "intermediate_steps": state.get("intermediate_steps", []) + [
                        (agent_outcome, output)
                    ],
                    "continue": "call_llm"
                }

            except Exception as e:
                error_msg = f"Error executing tool {tool_name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # Send error to callback
                await self.callback_handler.on_llm_error(error_msg)
                
                # Return error for agent's next step
                return {
                    "intermediate_steps": state.get("intermediate_steps", []) + [
                        (agent_outcome, f"Tool execution failed: {str(e)}")
                    ],
                    "continue": "call_llm"
                }

        # Handle dictionary response (legacy format)
        if isinstance(agent_outcome, dict):
            tool_name = agent_outcome.get("action")
            tool_input = agent_outcome.get("action_input", {})
            
            if tool_name == "Final Answer":
                return {
                    "agent_outcome": AgentFinish(
                        return_values={"output": tool_input},
                        log=str(tool_input)
                    ),
                    "continue": "final_response"
                }

            # Convert to AgentAction and recurse
            agent_action = AgentAction(
                tool=tool_name,
                tool_input=tool_input,
                log=str(agent_outcome)
            )
            return await self._tool_call_node({**state, "agent_outcome": agent_action})

        error_msg = f"Invalid agent outcome type: {type(agent_outcome)}"
        logger.error(error_msg)
        return {
            "agent_outcome": AgentFinish(
                return_values={"output": error_msg},
                log=error_msg
            ),
            "continue": "final_response"
        }

    def _should_continue_node(self, state):
        """Determines if the agent should continue or give a final response."""
        agent_outcome = state["agent_outcome"]

        if isinstance(agent_outcome, AgentFinish):
            return {"continue": "final_response"}
        elif isinstance(agent_outcome, AgentAction):
            return {"continue": "tool_call"}
        elif isinstance(agent_outcome, dict) and "continue" in agent_outcome:
            return {"continue": agent_outcome["continue"]}
        
        return {"continue": "tool_call"}

    async def _final_response_node(self, state):
        """Node to handle final responses."""
        agent_outcome = state["agent_outcome"]

        if isinstance(agent_outcome, AgentFinish):
            return {
                "output": agent_outcome.return_values["output"]
            }
        elif isinstance(agent_outcome, dict):
            if "output" in agent_outcome:
                return {"output": agent_outcome["output"]}
            else:
                return {"output": str(agent_outcome)}
        else:
            return {"output": str(agent_outcome)}

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Process a message using the agent"""
        if not self.langraph:
            raise ValueError("LangGraph not initialized")

        if self.processing:
            return None

        try:
            self.processing = True

            # Store the user message
            self.message_history.add_user_message(message)

            # Handle message editing
            if is_edit:
                await self._handle_message_edit()

            # Format input for agent
            input_data = {
                "messages": self.message_history.messages,
                "input": message,
                "llm": self.llm,
                "tools": await self._load_tools(),
                "intermediate_steps": [],
                "agent": self.agent,
                "client_data": self.client_data
            }

            # Run the graph synchronously
            result = await self.langraph.ainvoke(input_data)
            
            logger.debug(f"Graph result type: {type(result)}")
            logger.debug(f"Graph result content: {result}")

            # Process the final result
            if isinstance(result, dict):
                if "output" in result:
                    final_response = result["output"]
                    await self.callback_handler.on_llm_new_token(final_response)
                    self.message_history.add_ai_message(final_response)
                elif "agent_outcome" in result:
                    agent_outcome = result["agent_outcome"]
                    if isinstance(agent_outcome, AgentFinish):
                        final_response = agent_outcome.return_values["output"]
                        await self.callback_handler.on_llm_new_token(final_response)
                        self.message_history.add_ai_message(final_response)
                    elif isinstance(agent_outcome, AgentAction):
                        # Handle tool execution result
                        tool_name = agent_outcome.tool
                        tool_input = agent_outcome.tool_input
                        await self.callback_handler.on_llm_new_token({
                            'tool': tool_name,
                            'input': tool_input
                        })

            return None

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.callback_handler.on_llm_error(str(e))
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