import logging
import traceback
from crewai.agents.parser import AgentAction, AgentFinish
from apps.agents.models import CrewExecution, Task
from ..utils.logging import log_crew_message
from ..messaging.execution_bus import ExecutionMessageBus

logger = logging.getLogger(__name__)

class TaskCallback:
    def __init__(self, execution_id):
        self.execution_id = execution_id
        self.current_task_index = None
        self.current_agent_role = None
        self.message_bus = ExecutionMessageBus(execution_id)

    def __call__(self, task_output):
        """Handle task callback from CrewAI."""
        try:
            logger.debug(f"TaskCallback called with task_output: {task_output}")
            logger.debug(f"Current task index: {self.current_task_index}")
            
            execution = CrewExecution.objects.get(id=self.execution_id)
            
            # Get the task ID based on task index
            ordered_tasks = Task.objects.filter(
                crewtask__crew=execution.crew
            ).order_by('crewtask__order')
            
            if self.current_task_index is not None and self.current_task_index < len(ordered_tasks):
                crewai_task_id = ordered_tasks[self.current_task_index].id
                self.current_agent_role = ordered_tasks[self.current_task_index].agent.role
            else:
                crewai_task_id = None
            
            if task_output.raw:
                logger.debug(f"Processing task output with index: {self.current_task_index}")
                # Log to database
                log_crew_message(
                    execution=execution,
                    content=task_output.raw,
                    agent=self.current_agent_role,
                    crewai_task_id=crewai_task_id,
                    task_index=self.current_task_index
                )

        except Exception as e:
            logger.error(f"Error in task callback: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

class StepCallback:
    def __init__(self, execution_id):
        self.execution_id = execution_id
        self.current_task_index = None
        self.current_agent_role = None
        self.message_bus = ExecutionMessageBus(execution_id)

    def __call__(self, step_output):
        """Handle step callback from CrewAI."""
        try:
            if isinstance(step_output, AgentFinish):
                logger.debug(f"StepCallback: Skipping AgentFinish output for task index: {self.current_task_index}")
                logger.debug(f"StepCallback: AgentFinish attributes: {vars(step_output)}")
                return
            else:
                logger.debug(f"StepCallback: Processing step output for task index: {self.current_task_index}")
                logger.debug(f"Step output: {step_output}")
            
            # Only process tool usage
            if isinstance(step_output, AgentAction):
                execution = CrewExecution.objects.get(id=self.execution_id)
                
                # Get the task ID based on task index
                ordered_tasks = Task.objects.filter(
                    crewtask__crew=execution.crew
                ).order_by('crewtask__order')
                
                if self.current_task_index is not None and self.current_task_index < len(ordered_tasks):
                    crewai_task_id = ordered_tasks[self.current_task_index].id
                    self.current_agent_role = ordered_tasks[self.current_task_index].agent.role
                else:
                    crewai_task_id = None

                # Log tool usage
                log_crew_message(
                    execution=execution,
                    content=f"Using tool: {step_output.tool}\nInput: {step_output.tool_input}",
                    agent=self.current_agent_role,
                    crewai_task_id=crewai_task_id,
                    task_index=self.current_task_index
                )
                
                if step_output.result:
                    # Log tool result
                    log_crew_message(
                        execution=execution,
                        content=f"Tool result: {step_output.result}",
                        agent=self.current_agent_role,
                        crewai_task_id=crewai_task_id,
                        task_index=self.current_task_index
                    )

        except Exception as e:
            logger.error(f"Error in step callback: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise