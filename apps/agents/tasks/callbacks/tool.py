import logging
from apps.agents.tools.base_tool import ToolUsageError
from crewai.utilities.events import on
from apps.agents.models import CrewExecution
from ..utils.logging import log_crew_message

logger = logging.getLogger(__name__)

@on(ToolUsageError)
def tool_error_callback(source, event: ToolUsageError):
    """
    This callback is triggered whenever a tool encounters an error during execution.

    Args:
        source: The source of the event (likely the ToolUsage instance).
        event (ToolUsageError): The ToolUsageError event containing error details.
    """
    execution_id = source.task.execution_id  # Assuming you've stored execution_id in the Task
    execution = CrewExecution.objects.get(id=execution_id)
    agent_role = event.agent_role

    error_message = f"Tool '{event.tool_name}' failed for agent '{agent_role}'."
    error_message += f"\n Error: {event.error}"
    error_message += f"\n Tool Arguments: {event.tool_args}"
    error_message += f"\n Run Attempts: {event.run_attempts}"
    error_message += f"\n Delegations: {event.delegations}"
    
    log_crew_message(execution, error_message, agent='Tool Error Callback')
    logger.error(error_message) 