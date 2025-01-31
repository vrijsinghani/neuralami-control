import logging
import os
from datetime import datetime
from django.core.files.storage import default_storage
from django.conf import settings
from crewai import Task as CrewAITask
from apps.agents.models import Task, Agent
from ..utils.tools import load_tool_in_task
from ..utils.logging import log_crew_message
from crewai import Task

logger = logging.getLogger(__name__)

def create_crewai_tasks(task_models, agents, execution):
    tasks = []
    for task_model in task_models:
        try:
            # Get and log the agent model details
            agent_model = Agent.objects.get(id=task_model.agent_id)
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

            optional_fields = ['output_json', 'output_pydantic', 'converter_cls']
            task_dict.update({field: getattr(task_model, field) for field in optional_fields if getattr(task_model, field) is not None})

            # Handle output_file
            if task_model.output_file:
                try:
                    # Generate a unique file path
                    description_part = task_model.description[:20]  # First 20 chars of description
                    timestamp = datetime.now().strftime("%y-%m-%d-%H-%M")
                    
                    # Get the file name and extension
                    file_name, file_extension = os.path.splitext(task_model.output_file)
                    
                    # Create the relative path
                    relative_path = os.path.join(
                        str(execution.user.id),
                        description_part,
                        f"{file_name}_{timestamp}{file_extension}"
                    )

                    # Get the full URL for the file
                    full_url = default_storage.url(relative_path)
                    
                    logger.debug(f"Output file will be saved to: {relative_path}")
                    log_crew_message(execution, f"Task output will be saved to: {full_url}", agent='System')

                    task_dict['output_file'] = relative_path

                except Exception as e:
                    logger.error(f"Error setting up output file path: {str(e)}", exc_info=True)
                    # Continue without output file if there's an error
                    pass

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

def create_writing_task():
    return Task(
        description="Write content to specified file",
        expected_output="SUCCESS: File 'fluffy-1.0.txt' written to 1/fluffy-1.0.txt (Length: 175 chars)",  # Match tool's success format
        agent=writer_agent,
        tools=[FileWriterTool(result_as_answer=True)],  # Force direct tool output
        max_retries=1  # Prevent infinite loops
    ) 