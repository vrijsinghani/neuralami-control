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
                # Format as a proper execution update
                event = {
                    'type': 'execution_update',
                    'execution_id': self.execution_id,
                    'crewai_task_id': crewai_task_id,
                    'status': execution.status,
                    'stage': {
                        'stage_type': 'task_output',
                        'title': 'Task Output',
                        'content': task_output.raw,
                        'status': 'completed',
                        'agent': self.current_agent_role
                    }
                }
                self.message_bus.publish('execution_update', event)
                
                # Log to database
                log_crew_message(
                    execution=execution,
                    content=task_output.raw,
                    agent=self.current_agent_role,
                    crewai_task_id=crewai_task_id
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
            # Only process tool usage, skip AgentFinish
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
                event = {
                    'type': 'execution_update',
                    'execution_id': self.execution_id,
                    'crewai_task_id': crewai_task_id,
                    'stage': {
                        'stage_type': 'tool_usage',
                        'title': f'Using Tool: {step_output.tool}',
                        'content': f'Tool: {step_output.tool}\nInput: {step_output.tool_input}',
                        'status': 'in_progress',
                        'agent': self.current_agent_role
                    }
                }
                self.message_bus.publish('execution_update', event)
                
                log_crew_message(
                    execution=execution,
                    content=f"Using tool: {step_output.tool}\nInput: {step_output.tool_input}",
                    agent=self.current_agent_role,
                    crewai_task_id=crewai_task_id
                )
                
                if step_output.result:
                    # Log tool result
                    event = {
                        'type': 'execution_update',
                        'execution_id': self.execution_id,
                        'crewai_task_id': crewai_task_id,
                        'stage': {
                            'stage_type': 'tool_result',
                            'title': 'Tool Result',
                            'content': step_output.result,
                            'status': 'completed',
                            'agent': self.current_agent_role
                        }
                    }
                    self.message_bus.publish('execution_update', event)
                    
                    log_crew_message(
                        execution=execution,
                        content=f"Tool result: {step_output.result}",
                        agent=self.current_agent_role,
                        crewai_task_id=crewai_task_id
                    )

        except Exception as e:
            logger.error(f"Error in step callback: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise