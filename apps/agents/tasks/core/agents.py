import logging
from functools import partial
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
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in ProxiedLLM call: {str(e)}")
            raise

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
                logger.debug(f"LLM field: {field}, value: {value}")
                if value:
                    agent_llm, _ = get_llm(value)
                    logger.debug(f"Agent LLM: {agent_llm}")
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