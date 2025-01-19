import logging
import os
from datetime import datetime
from django.conf import settings
from crewai import Task as CrewAITask
from apps.agents.models import Task, Agent
from ..utils.tools import load_tool_in_task
from ..utils.logging import log_crew_message

logger = logging.getLogger(__name__)

def create_crewai_tasks(task_models, agents, execution):
    tasks = []
    for task_model in task_models:
        try:
            # Log the task details
            # logger.debug(f"""
# Task details:
# - ID: {task_model.id}
# - Description: {task_model.description}
# - Agent ID: {task_model.agent_id}
# """)
            
            # Get and log the agent model details
            agent_model = Agent.objects.get(id=task_model.agent_id)
#             logger.info(f"""
# Agent Model details:
# - ID: {agent_model.id}
# - Role: {agent_model.role}
# """)
            
            # Log available CrewAI agents
            # logger.info("Available CrewAI agents:")
            # for agent in agents:
            #     logger.info(f"- Agent Role: {agent.role}")

            # Associate the Task with the CrewExecution
            task_model.crew_execution = execution
            task_model.save()

            # Try to find matching agent
            crewai_agent = next((agent for agent in agents if agent.role == agent_model.role), None)
            
            if not crewai_agent:
                logger.warning(f"""
No matching CrewAI agent found for task {task_model.id}
Looking for role: {agent_model.role}
Available roles: {[agent.role for agent in agents]}
""")
                continue

            task_tools = []
            for tool_model in task_model.tools.all():
                tool = load_tool_in_task(tool_model)
                if tool:
                    task_tools.append(tool)
            human_input = bool(task_model.human_input) if task_model.human_input is not None else False
            task_dict = {
                'description': task_model.description,
                'agent': crewai_agent,
                'expected_output': task_model.expected_output,
                'async_execution': task_model.async_execution,
                'human_input': human_input,
                'tools': task_tools,
                'execution_id': execution.id
            }
            # logger.info(f"Task dict: {task_dict}")
            optional_fields = ['output_json', 'output_pydantic', 'converter_cls']
            task_dict.update({field: getattr(task_model, field) for field in optional_fields if getattr(task_model, field) is not None})

            # Handle output_file separately
            if task_model.output_file:
                description_part = task_model.description[:20]  # Adjust the slice as needed
                
                # Generate a pithy timestamp
                timestamp = datetime.now().strftime("%y-%m-%d-%H-%M")
                
                # Get the file name and extension
                file_name, file_extension = os.path.splitext(task_model.output_file)
                
                # Append the timestamp to the file name
                new_file_name = f"{file_name}_{timestamp}{file_extension}"

                # Construct the full path using MEDIA_ROOT
                full_path = os.path.join(settings.MEDIA_URL, str(execution.user.id), description_part, new_file_name)
                logger.debug(f"Full path for output_file: {full_path}")
                log_crew_message(execution, f"Task output will be saved to: {full_path}", agent='System')

                task_dict['output_file'] = full_path

            if task_model.human_input:
                logger.debug(f"Creating task with human input enabled: {task_model.description}")
                # Add specific configuration for human input tasks
                task_dict.update({
                    'require_human_input': True,
                    'process_human_input': True
                })
            tasks.append(CrewAITask(**task_dict))
            logger.debug(f"CrewAITask created successfully for task: {task_model.id}")
        except Exception as e:
            logger.error(f"Error creating CrewAITask for task {task_model.id}: {str(e)}", exc_info=True)
    return tasks 