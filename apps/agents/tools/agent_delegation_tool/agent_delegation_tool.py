import logging
from typing import Type, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
import json

from apps.agents.tools.base_tool import BaseTool
# Import necessary components for agent execution
from apps.agents.models import Agent as AgentModel, Tool as ToolModel
from apps.common.utils import get_llm
# Use load_tool from tool_utils for consistency
from apps.agents.utils.tool_utils import load_tool
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage
# Import LangChain tool types for conversion
from langchain.tools import Tool, StructuredTool

logger = logging.getLogger(__name__)

class AgentDelegationInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )

    agent_id: int = Field(description="The database ID of the agent to delegate the task to.")
    prompt: str = Field(description="The specific task, question, or instruction for the delegated agent.")
    # include_parent_history: bool = Field(default=False, description="Flag to include parent agent\'s history.") # Keep it simple for now

class AgentDelegationTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )

    name: str = "Agent Delegation Tool"
    # Define description using Field to satisfy Pydantic initialization
    description: str = Field(default="Delegates a task or question to another specified agent (by ID) and returns its response. Use the agent_id parameter to specify the target agent.")
    args_schema: Type[BaseModel] = AgentDelegationInput
    # parent_agent_id: Optional[int] = None # Potentially needed for recursion check later

    def _run(self, agent_id: int, prompt: str, **kwargs: Any) -> Any:
        """Use the tool to delegate a task to another agent."""
        logger.info(f"AgentDelegationTool invoked: Delegating prompt \'{prompt[:50]}...\' to agent ID {agent_id}")

        # --- Implementation Steps (from PRD) ---
        # 1. Basic Recursion Check (Future enhancement, placeholder)
        # parent_agent_id = kwargs.get('parent_agent_id', None) # How to get parent ID? Needs passing maybe.
        # if parent_agent_id and agent_id == parent_agent_id:
        #     logger.warning(f"Recursion detected: Agent {parent_agent_id} attempted to delegate back to itself via agent {agent_id}.")
        #     return "Error: Recursive delegation detected. Cannot delegate task back to the calling agent."

        # 2. Call helper function _execute_delegated_agent
        try:
            # Pass necessary context if needed in future, e.g., parent_agent_id
            result = self._execute_delegated_agent(agent_id, prompt)
            logger.info(f"AgentDelegationTool completed for agent ID {agent_id}. Result: {str(result)[:100]}...")
            return result
        except ObjectDoesNotExist:
            logger.error(f"AgentDelegationTool Error: Agent with ID {agent_id} not found.")
            return f"Error: Agent with ID {agent_id} not found."
        except Exception as e:
            logger.error(f"Error executing AgentDelegationTool for agent ID {agent_id}: {e}", exc_info=True)
            return f"Error: Failed to execute delegated task for agent {agent_id}. Reason: {e}"

    def _execute_delegated_agent(self, agent_id: int, prompt: str) -> str:
        """
        Helper function to set up and run the delegated agent synchronously.
        """
        logger.debug(f"Executing delegated agent ID: {agent_id} with prompt: \'{prompt[:50]}...\'")

        # 1. Fetch Agent model (synchronously)
        try:
            agent_model = AgentModel.objects.get(id=agent_id)
            logger.debug(f"Successfully fetched agent model: {agent_model.name} (ID: {agent_id})")
        except AgentModel.DoesNotExist:
            # This specific exception is caught and re-raised for handling in _run
            raise ObjectDoesNotExist(f"Agent with ID {agent_id} not found.")
        except Exception as e:
            logger.error(f"Unexpected error fetching agent {agent_id}: {e}", exc_info=True)
            return f"Error: Could not fetch agent details for ID {agent_id}."

        # 2. Load LLM
        try:
            # We don't need token tracking callback here for the tool execution
            child_llm, _ = get_llm(agent_model.llm)
            if not child_llm:
                 raise ValueError("Failed to load LLM specified for the agent.")
            logger.debug(f"Successfully loaded LLM for agent {agent_id}")
        except Exception as e:
            logger.error(f"Error loading LLM for agent {agent_id}: {e}", exc_info=True)
            return f"Error: Could not load LLM for agent {agent_id}."

        # 3. Load Tools synchronously
        tools = []
        try:
            for tool_model in agent_model.tools.all():
                try:
                    # Use load_tool which handles instantiation from the model
                    loaded_tool = load_tool(tool_model)
                    if loaded_tool:
                        # TODO: Potentially apply AgentToolSetting overrides like in create_crewai_agents if needed
                        # For now, load the basic tool
                        tools.append(loaded_tool)
                        logger.debug(f"Loaded tool '{tool_model.name}' for agent {agent_id}")
                    else:
                        logger.warning(f"Failed to load tool instance for '{tool_model.name}' (ID: {tool_model.id}) for agent {agent_id}")
                except Exception as tool_load_error:
                    logger.error(f"Error loading tool '{tool_model.name}' (ID: {tool_model.id}) for agent {agent_id}: {tool_load_error}", exc_info=True)
                    # Decide whether to proceed without the tool or fail the whole delegation
                    # For now, let's skip the failing tool and log a warning
                    logger.warning(f"Skipping tool '{tool_model.name}' due to loading error.")
            logger.info(f"Loaded {len(tools)} tools for agent {agent_id}")
        except Exception as e:
            logger.error(f"Error accessing or iterating tools for agent {agent_id}: {e}", exc_info=True)
            return f"Error: Could not load tools for agent {agent_id}."

        # 3.5 Convert loaded tools to LangChain format
        langchain_tools = []
        for tool_instance in tools:
            try:
                if hasattr(tool_instance, 'args_schema') and tool_instance.args_schema:
                    # Use StructuredTool if args_schema is present
                    lc_tool = StructuredTool(
                        name=tool_instance.name,
                        description=tool_instance.description, # Use instance description
                        func=tool_instance.run, # Use the synchronous run method
                        coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None,
                        args_schema=tool_instance.args_schema
                    )
                else:
                    # Use standard Tool if no args_schema
                    lc_tool = Tool(
                        name=tool_instance.name,
                        description=tool_instance.description, # Use instance description
                        func=tool_instance.run,
                        coroutine=tool_instance.arun if hasattr(tool_instance, 'arun') else None
                    )
                langchain_tools.append(lc_tool)
            except Exception as conversion_error:
                logger.error(f"Error converting tool '{tool_instance.name}' to LangChain format: {conversion_error}", exc_info=True)
                logger.warning(f"Skipping tool '{tool_instance.name}' due to conversion error.")
        logger.info(f"Converted {len(langchain_tools)} tools to LangChain format for agent {agent_id}")

        # 4. Build LangChain prompt, agent, and AgentExecutor
        try:
            # Construct a simple system message from agent details
            base_system_content = f"Role: {agent_model.role}\nGoal: {agent_model.goal}\nBackstory: {agent_model.backstory}"
            if agent_model.system_template:
                # If a specific system template exists, prioritize it
                base_system_content = f"{agent_model.system_template}\n\n{base_system_content}"

            # --- Add Credentials Context --- 
            sc_credentials_json = "null" # Default if not found
            sc_instructions = ""
            try:
                # Fetch SC credentials (adjust setting names if needed)
                sc_client_id = getattr(settings, 'GOOGLE_OAUTH_SC_CLIENT_ID', None)
                sc_client_secret = getattr(settings, 'GOOGLE_OAUTH_SC_CLIENT_SECRET', None)
                
                if sc_client_id and sc_client_secret:
                    sc_credentials = {
                        # Include necessary fields expected by the tool, 
                        # e.g., client_id, client_secret. Add refresh/access tokens if needed and available.
                        "client_id": sc_client_id,
                        "client_secret": sc_client_secret,
                        # Placeholder: Add refresh_token etc. if needed by the tool's auth flow
                    }
                    sc_credentials_json = json.dumps(sc_credentials)
                    sc_instructions = f"""\n\nIMPORTANT OAUTH CREDENTIALS:
*   **Search Console Credentials:** ```json
{sc_credentials_json}
```
*   When using Google Search Console tools (like GoogleRankingsTool), you MUST provide the full Search Console Credentials dictionary shown above in the 'search_console_credentials' parameter of your tool input JSON blob."""
                else:
                    logger.warning(f"AgentDelegationTool: Search Console Client ID or Secret not found in settings. Child agent {agent_id} may fail on SC tools.")
            except Exception as cred_e:
                 logger.error(f"AgentDelegationTool: Error fetching SC credentials for child agent {agent_id}: {cred_e}", exc_info=True)
                 sc_instructions = "\n\nWarning: Could not automatically fetch Search Console credentials. Tool calls may fail."
            # --- End Credentials Context ---

            # Format tools for prompt using the LangChain-formatted tools
            tool_descriptions = [f"{lc_tool.name}: {lc_tool.description}" for lc_tool in langchain_tools]
            tool_names = [lc_tool.name for lc_tool in langchain_tools]
            
            # Create the structured chat prompt template with proper JSON formatting
            system_template = f'''{base_system_content}

You have access to the following tools:

{{tools}}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).

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
$JSON_BLOB

Observation: action result
... (repeat Thought/Action/Observation N times)
Thought: I know what to respond
Action:
{{{{
"action": "Final Answer",
"action_input": "Final response to human"
}}}}


Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate.

{sc_instructions} # Add credential instructions here
'''

            # Create the prompt with the system template
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_template),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}\n\n{agent_scratchpad}")
            ])
            
            # Partially fill system-level variables
            prompt = prompt.partial(
                tools="\n".join(tool_descriptions),
                tool_names=", ".join(tool_names)
            )

            # Create the agent using LangChain-formatted tools
            structured_agent = create_structured_chat_agent(
                llm=child_llm,
                tools=langchain_tools,
                prompt=prompt
            )

            # Create the AgentExecutor using LangChain-formatted tools
            agent_executor = AgentExecutor.from_agent_and_tools(
                agent=structured_agent,
                tools=langchain_tools,
                verbose=agent_model.verbose, # Use agent's verbosity setting
                max_iterations=agent_model.max_iter or 10, # Use agent's max_iter or default to 10
                handle_parsing_errors=True, # Handle potential output parsing errors
                # No memory needed for single-shot tool execution
                # No complex callbacks needed here
            )
            logger.debug(f"Created agent executor for agent {agent_id}")

        except Exception as e:
            logger.error(f"Error creating agent execution components for agent {agent_id}: {e}", exc_info=True)
            return f"Error: Failed to set up execution environment for agent {agent_id}."

        # 5. Invoke executor.invoke()
        try:
            logger.info(f"Invoking agent {agent_id} executor with prompt: '{prompt[:50]}...'")
            response = agent_executor.invoke({"input": prompt})
            output = response.get('output', None)

            if output is None:
                logger.error(f"Agent {agent_id} execution finished but produced no output. Response: {response}")
                return f"Error: Agent {agent_id} finished execution but produced no output."

            logger.info(f"Agent {agent_id} execution successful. Output: {str(output)[:100]}...")
            return str(output) # Ensure output is a string

        except Exception as e:
            logger.error(f"Error during agent {agent_id} execution: {e}", exc_info=True)
            # Provide a more informative error message if possible
            error_message = f"Error: Agent {agent_id} failed during execution. Reason: {e}"
            # Check for specific common errors if needed (e.g., max iterations)
            if "Agent stopped due to max iterations" in str(e):
                error_message = f"Error: Agent {agent_id} stopped due to reaching the maximum iteration limit."
            return error_message

        # Placeholder return until implementation is complete
        # return f"Placeholder: Agent {agent_id} ({agent_model.name}) fetched with LLM and {len(tools)} tools. Ready to process prompt: \'{prompt}\'"

    async def _arun(self, agent_id: int, prompt: str, **kwargs: Any) -> Any:
        """Asynchronous execution (Not Implemented)."""
        logger.warning("Asynchronous execution (_arun) is not implemented for AgentDelegationTool.")
        raise NotImplementedError("AgentDelegationTool does not support async execution yet.")
