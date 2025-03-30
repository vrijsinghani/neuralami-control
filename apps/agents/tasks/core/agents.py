import logging
from functools import partial
import json
from crewai import Agent
from crewai.llm import LLM
from ..utils.tools import load_tool_in_task
from ..handlers.input import human_input_handler
from ..callbacks.execution import StepCallback
from apps.common.utils import get_llm

logger = logging.getLogger(__name__)

class ProxiedLLM(LLM):
    """Wrapper to make ChatOpenAI work with CrewAI"""
    def __init__(self, llm):
        self.llm = llm
        super().__init__(
            model=llm.model_name,
            temperature=llm.temperature,
        )
        
    def call(self, messages, *args, **kwargs):
        """
        Enhanced call method that safely handles various input formats and prevents errors
        from propagating to CrewAI's error handling code where they might cause the
        'ConverterError object is not subscriptable' issue.
        """
        if not messages:
            logger.error("Error in ProxiedLLM call: Empty or None messages provided")
            return "Error: No messages provided to the language model."
        
        try:
            # Log the original messages for debugging and log the last two messages 
            logger.debug(f"ProxiedLLM received {len(messages)} messages")
            #logger.debug(f"Last messages: {messages[-1:]}")
            
            # Create a deep copy of messages to avoid modifying the original
            sanitized_messages = []
            
            for message in messages:
                # If message isn't a dict, convert it to one
                if not isinstance(message, dict):
                    sanitized_message = {"role": "user", "content": str(message)}
                else:
                    sanitized_message = message.copy()
                
                # Handle content field specially
                if 'content' in sanitized_message:
                    content = sanitized_message['content']
                    
                    # Handle None content
                    if content is None:
                        sanitized_message['content'] = ""
                        sanitized_messages.append(sanitized_message)
                        continue
                    
                    # If content is already a string, keep it as is
                    if isinstance(content, str):
                        sanitized_messages.append(sanitized_message)
                        continue
                    
                    # Handle complex content types (lists, dicts, etc.)
                    try:
                        # Handle code interpreter special case
                        if isinstance(content, list) and len(content) > 0:
                            if isinstance(content[0], dict) and 'code' in content[0]:
                                # Create a simplified representation
                                code = content[0].get('code', '')
                                libraries = content[0].get('libraries_used', [])
                                simplified = {"code": code, "libraries_used": libraries}
                                sanitized_message['content'] = json.dumps(simplified)
                            else:
                                # Convert list to JSON string
                                sanitized_message['content'] = json.dumps(content)
                        elif isinstance(content, dict):
                            # Convert dict to JSON string
                            sanitized_message['content'] = json.dumps(content)
                        else:
                            # Convert any other type to string
                            sanitized_message['content'] = str(content)
                    except Exception as e:
                        # If all else fails, use string representation
                        logger.warning(f"Error serializing message content: {str(e)}")
                        sanitized_message['content'] = str(content)
                
                sanitized_messages.append(sanitized_message)
            
            # Log sanitized messages
            logger.debug(f"Processed {len(sanitized_messages)} messages for LLM")
            # log the first 200 chars of the latest message
            logger.debug(f"Last message: {sanitized_messages[-1]['content'][:200]}")
            # log the first 200 chars of the first message
            logger.debug(f"First message: {sanitized_messages[0]['content'][:200]}")
            
            # Invoke the LLM with the sanitized messages
            response = self.llm.invoke(sanitized_messages)
            # log the first 200 chars of the response
            logger.debug(f"Response: {response.content[:200]}")
            return response.content
        
        except Exception as e:
            # Detailed error logging but return a simple string response
            # This ensures we never propagate an exception object that could cause
            # the 'not subscriptable' error in CrewAI
            logger.error(f"Error in ProxiedLLM call: {str(e)}", exc_info=True)
            return f"Error processing request: {str(e)}"

def create_crewai_agents(agent_models, execution_id):
    agents = []
    for agent_model in agent_models:
        try:
            agent_params = {
                'role': agent_model.role,
                'goal': agent_model.goal,
                'backstory': agent_model.backstory,
                'verbose': agent_model.verbose,
                'allow_delegation': agent_model.allow_delegation,
                'step_callback': StepCallback(execution_id),
                'human_input_handler': partial(human_input_handler, execution_id=execution_id),
                'tools': [],
                'execution_id': execution_id
            }

            # Handle LLM fields for Agent
            llm_fields = ['llm', 'function_calling_llm']
            for field in llm_fields:
                value = getattr(agent_model, field)
                #logger.debug(f"LLM field: {field}, value: {value}")
                if value:
                    agent_llm, _ = get_llm(value)
                    #logger.debug(f"Agent LLM: {agent_llm}")
                    # Wrap the ChatOpenAI instance for CrewAI compatibility
                    agent_params[field] = ProxiedLLM(agent_llm)

            # Load tools with their settings
            for tool in agent_model.tools.all():
                loaded_tool = load_tool_in_task(tool)
                if loaded_tool:
                    # Get tool settings
                    tool_settings = agent_model.get_tool_settings(tool)
                    if tool_settings and tool_settings.force_output_as_result:
                        # Apply the force output setting
                        loaded_tool = type(loaded_tool)(
                            result_as_answer=True,
                            **{k: v for k, v in loaded_tool.__dict__.items() if k != 'result_as_answer'}
                        )
                    agent_params['tools'].append(loaded_tool)
                else:
                    logger.warning(f"Failed to load tool {tool.name} for agent {agent_model.name}")

            optional_params = ['max_iter', 'max_rpm', 'system_template', 'prompt_template', 'response_template']
            agent_params.update({param: getattr(agent_model, param) for param in optional_params if getattr(agent_model, param) is not None})
            
            agent = Agent(**agent_params)
            logger.debug(f"CrewAI Agent created successfully for agent id: {agent_model.id} with {len(agent_params['tools'])} tools")
            agents.append(agent)
        except Exception as e:
            logger.error(f"Error creating CrewAI Agent for agent {agent_model.id}: {str(e)}")
    return agents 