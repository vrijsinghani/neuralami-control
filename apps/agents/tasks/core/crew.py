import logging
import traceback
from datetime import datetime
import re
import os
from functools import partial
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from crewai import Crew
from crewai.agents.agent_builder.base_agent_executor_mixin import CrewAgentExecutorMixin
from apps.agents.models import CrewExecution, ExecutionStage, CrewOutput, Task
from ..utils.logging import log_crew_message, update_execution_status
from .agents import create_crewai_agents
from .tasks import create_crewai_tasks
from ..callbacks.execution import StepCallback, TaskCallback
from ..handlers.input import human_input_handler
from apps.common.utils import get_llm
import time
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from apps.seo_manager.models import Client
from apps.file_manager.storage import PathManager
from apps.organizations.utils import OrganizationContext
from contextlib import nullcontext
from django.utils import timezone

logger = logging.getLogger(__name__)

def clean_text(text, field_name):
    """Generic function to clean text by escaping JSON-like structures and removing problematic characters"""
    if not text:
        return text

    #logger.debug(f"Original {field_name}: {repr(text)}")

    try:
        # First remove any problematic whitespace/newline characters
        text = text.strip()

        # Handle the specific {{{{{ }}}}} format used in examples
        def escape_json_block(match):
            content = match.group(1)
            # Remove extra whitespace and newlines within the JSON
            content = ' '.join(content.split())
            return f"{{{{{{{{ {content} }}}}}}}}"

        # First pass: Handle the example blocks with multiple braces
        text = re.sub(r'{{{{{(.*?)}}}}}', escape_json_block, text, flags=re.DOTALL)

        # Second pass: Handle any remaining JSON-like structures
        def escape_json_block(match):
            content = match.group(1)
            # Remove extra whitespace and newlines within the JSON
            content = ' '.join(content.split())
            return f"{{{{ {content} }}}}"

        # Handle regular JSON blocks
        text = re.sub(r'(?<!{){([^{].*?)}(?!})', escape_json_block, text, flags=re.DOTALL)

        # Final pass: Escape any remaining single braces that might be format strings
        text = re.sub(r'(?<!{){(?!{)', '{{', text)
        text = re.sub(r'(?<!})}(?!})', '}}', text)

        #logger.debug(f"Cleaned {field_name}: {repr(text)}")
        return text

    except Exception as e:
        logger.error(f"Error cleaning ba{field_name}: {str(e)}")
        logger.error(f"Problematic {field_name}: {repr(text)}")
        # Return a safely escaped version as fallback
        return text.replace("{", "{{").replace("}", "}}")

def initialize_crew(execution):
    """Initialize a CrewAI crew instance from a CrewExecution object"""
    try:
        # Create regular agents (excluding manager)
        regular_agents = list(execution.crew.agents.all())
        #logger.debug(f"Regular agents: {regular_agents}")
        # Create CrewAI agents for regular agents
        agents = create_crewai_agents(regular_agents, execution.id)
        #logger.debug(f"Created CrewAI agents: {agents}")
        if not agents:
            raise ValueError("No valid agents created")
            
        # Create manager agent separately if it exists
        manager_agent = None
        if execution.crew.manager_agent:
            manager_agents = create_crewai_agents([execution.crew.manager_agent], execution.id)
            if manager_agents:
                manager_agent = manager_agents[0]
        
        # Fetch and order the tasks
        ordered_tasks = Task.objects.filter(
            crew=execution.crew
        ).order_by('crewtask__order')
        
        tasks = create_crewai_tasks(ordered_tasks, agents, execution)
        if not tasks:
            raise ValueError("No valid tasks for crew execution")

        # Handle LLM fields first
        llm_fields = ['manager_llm', 'function_calling_llm', 'planning_llm']
        llm_params = {}
        for field in llm_fields:
            value = getattr(execution.crew, field)
            if value:
                #logger.debug(f"Using LLM: {value}")
                crew_llm, _ = get_llm(value)
                llm_params[field] = crew_llm

        # Build crew parameters
        crew_params = {
            'agents': agents,
            'tasks': tasks,
            'step_callback': StepCallback(execution.id),
            'task_callback': TaskCallback(execution.id),
            'process': execution.crew.process,
            'verbose': execution.crew.verbose,
            'execution_id': str(execution.id),
            **llm_params  # Add LLM parameters
        }

        # Add manager agent if it exists
        if manager_agent:
            crew_params['manager_agent'] = manager_agent

        # Add optional parameters if they exist
        optional_params = [
            'memory', 'max_rpm', 'language', 'language_file', 'full_output',
            'share_crew', 'output_log_file', 'planning', 'manager_callbacks', 
            'prompt_file', 'cache', 'embedder'
        ]

        for param in optional_params:
            value = getattr(execution.crew, param, None)
            if value is not None:
                crew_params[param] = value

        # Create and return the crew instance
        # logger.debug(f"Creating Crew with parameters: {crew_params}")
        crew = Crew(**crew_params)
        
        if not crew:
            raise ValueError("Failed to create Crew instance")
            
        return crew
        
    except Exception as e:
        logger.error(f"Error in initialize_crew: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise

def get_client_data(client):
    """Helper function to get formatted client data with analytics credentials"""
    if not client:
        logger.warning("get_client_data called with None client")
        return {}
    
    # Format SEO projects into a readable string
    seo_projects_list = []
    for project in client.seo_projects.all().order_by('-implementation_date'):
        project_str = (
            f"Project: {project.title}\n"
            f"Description: {project.description}\n"
            f"Status: {project.status}\n"
            f"Implementation Date: {project.implementation_date.isoformat() if project.implementation_date else 'Not set'}\n"
            f"Completion Date: {project.completion_date.isoformat() if project.completion_date else 'Not set'}"
        )
        seo_projects_list.append(project_str)
    
    seo_projects_str = "\n\n".join(seo_projects_list) if seo_projects_list else ""
    
    client_data = {
        'client_id': client.id,
        'client_name': client.name,
        'client_website_url': client.website_url,
        'client_business_objectives': '\n'.join(str(obj) for obj in client.business_objectives) if client.business_objectives else '',
        'client_target_audience': client.target_audience,
        'client_profile': client.client_profile,
        'client_seo_projects': seo_projects_str,
    }
    
    # Add Google Analytics credentials if available
    try:
        if hasattr(client, 'ga_credentials') and client.ga_credentials:
            ga_creds = client.ga_credentials
            
            # Try to get property_id using get_property_id() method if available
            if hasattr(ga_creds, 'get_property_id') and callable(getattr(ga_creds, 'get_property_id')):
                try:
                    property_id = ga_creds.get_property_id()
                    client_data['analytics_property_id'] = str(property_id) if property_id is not None else ''
                    logger.debug(f"Got property_id '{property_id}' using get_property_id() method")
                except Exception as e:
                    logger.warning(f"Failed to get property_id using get_property_id() method: {e}")
                    client_data['analytics_property_id'] = ''
            else:
                # Fallback to direct attribute access
                client_data['analytics_property_id'] = getattr(ga_creds, 'property_id', '')
                
                # Fallback to view_id for older GA3 structure
                if not client_data['analytics_property_id'] and hasattr(ga_creds, 'view_id'):
                    client_data['analytics_property_id'] = getattr(ga_creds, 'view_id', '')
                    logger.debug(f"Using view_id as fallback for property_id")
            
            # Create actual credentials dictionary with real values
            client_data['analytics_credentials'] = {
                'ga_client_id': getattr(ga_creds, 'ga_client_id', ''),
                'client_secret': getattr(ga_creds, 'client_secret', ''), 
                'refresh_token': getattr(ga_creds, 'refresh_token', ''),
                'token_uri': getattr(ga_creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                'access_token': getattr(ga_creds, 'access_token', '')
            }
            
            # Log safely without exposing sensitive data
            logger.debug(f"Added Google Analytics credentials for client {client.name} (ID: {client.id})")
            
            # Add warning for missing critical fields
            missing_fields = []
            for field in ['ga_client_id', 'client_secret', 'refresh_token']:
                if not getattr(ga_creds, field, ''):
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"Missing critical Analytics credential fields for client {client.name}: {', '.join(missing_fields)}")
        else:
            logger.debug(f"Client {client.name} (ID: {client.id}) has no Google Analytics credentials")
    except Exception as e:
        logger.error(f"Error adding Google Analytics credentials for client {client.name}: {str(e)}")
    
    # Add Search Console credentials if available
    try:
        if hasattr(client, 'sc_credentials') and client.sc_credentials:
            sc_creds = client.sc_credentials
            
            # Use the get_property_url method properly
            try:
                if hasattr(sc_creds, 'get_property_url') and callable(getattr(sc_creds, 'get_property_url')):
                    property_url = sc_creds.get_property_url()
                    client_data['search_console_property_url'] = property_url if property_url else ''
                    logger.debug(f"Got property_url using get_property_url() method")
                else:
                    # Fallback to direct attribute access
                    property_url = getattr(sc_creds, 'property_url', '') or getattr(sc_creds, 'property_id', '')
                    client_data['search_console_property_url'] = property_url
            except Exception as e:
                logger.error(f"Error calling get_property_url: {str(e)}")
                # Fallback to direct attribute access
                property_url = getattr(sc_creds, 'property_url', '') or getattr(sc_creds, 'property_id', '')
                client_data['search_console_property_url'] = property_url
            
            if not property_url:
                logger.warning(f"Client {client.name} has Search Console credentials but no valid property URL")
            
            # Create actual credentials dictionary with real values
            client_data['search_console_credentials'] = {
                'sc_client_id': getattr(sc_creds, 'sc_client_id', ''),
                'client_secret': getattr(sc_creds, 'client_secret', ''),
                'refresh_token': getattr(sc_creds, 'refresh_token', ''),
                'token_uri': getattr(sc_creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                'access_token': getattr(sc_creds, 'access_token', '')
            }
            
            # Log safely without exposing sensitive data
            logger.debug(f"Added Search Console credentials for client {client.name} (ID: {client.id})")
            
            # Add warning for missing critical fields
            missing_fields = []
            for field in ['sc_client_id', 'client_secret', 'refresh_token']:
                if not getattr(sc_creds, field, ''):
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"Missing critical Search Console credential fields for client {client.name}: {', '.join(missing_fields)}")
        else:
            logger.debug(f"Client {client.name} (ID: {client.id}) has no Search Console credentials")
    except Exception as e:
        logger.error(f"Error adding Search Console credentials for client {client.name}: {str(e)}")
    
    # Log the available keys for debugging
    logger.debug(f"Client data keys available for crew: {', '.join(client_data.keys())}")
    
    return client_data

# Note: To use credentials in task descriptions, reference them like:
# "Task: Analyze traffic using Google Analytics credentials: {analytics_credentials} 
# and property ID: {analytics_property_id}, along with Search Console data using
# credentials: {search_console_credentials} and property URL: {search_console_property_url}"
#
# Example task description for CrewAI tasks:
# ```
# Task:
# Perform a comprehensive analysis of {client_name}'s website traffic patterns.
# 
# Details:
# - Current Date: {current_date}
# - Client Website: {client_website_url}
# - Client ID: {client_id}
# - Google Analytics Property ID: {analytics_property_id}
# - Search Console Property URL: {search_console_property_url}
# 
# Use the Google Analytics credentials and Search Console credentials provided below:
# 
# Google Analytics Credentials:
# {analytics_credentials}
# 
# Search Console Credentials:
# {search_console_credentials}
# 
# First, analyze traffic trends from Google Analytics. Then, examine keyword performance
# from Search Console. Finally, provide actionable recommendations based on your findings.
# ```
def run_crew(task_id, crew, execution):
    """Run the crew and handle the execution"""
    try:
        # Update to running status
        update_execution_status(execution, 'RUNNING')
        
        # Create execution stage for running
        ExecutionStage.objects.create(
            execution=execution,
            stage_type='task_execution',
            title='Running Task',
            content=f'Executing tasks for crew {crew.name}',
            status='in_progress'
        )
        
        # Get crew inputs with all task-specific data
        inputs = {
            'execution_id': execution.id,
            'current_date': datetime.now().strftime("%Y-%m-%d"),
        }
        
        # Add conversation history if available
        conversation_history = execution.get_conversation_history()
        if conversation_history:
            # Convert conversation history to string if it's a list to avoid interpolation errors
            if isinstance(conversation_history, list):
                inputs['conversation_history'] = "\n".join([str(msg) for msg in conversation_history])
            else:
                inputs['conversation_history'] = str(conversation_history)
        
        # Only add client-specific inputs if client exists
        if execution.client:
            inputs.update(get_client_data(execution.client))
        
        # Create callback instances
        step_callback = StepCallback(execution.id)
        task_callback = TaskCallback(execution.id)
        
        # Monkey patch the crew's _execute_tasks method to track current task
        original_execute_tasks = crew._execute_tasks
        
        def execute_tasks_with_tracking(*args, **kwargs):
            task_outputs = []
            futures = []
            last_sync_output = None
            
            for task_index, task in enumerate(crew.tasks):
                #logger.debug(f"Starting task {task_index}")
                
                # Get the agent and continue with original logic
                agent_to_use = crew._get_agent_to_use(task)
                if not agent_to_use:
                    raise ValueError(f"No agent available for task: {task.description}")
                
                # Set current task index in callbacks BEFORE execution
                step_callback.current_task_index = task_index
                task_callback.current_task_index = task_index
                step_callback.current_agent_role = agent_to_use.role
                task_callback.current_agent_role = agent_to_use.role
                
                # Update execution status with current task index
                
                # Create or update agent executor with callbacks and human input handler
                if not agent_to_use.agent_executor:
                    logger.debug(f"Creating agent executor for {agent_to_use.role}")
                    logger.debug(f"Agent LLM before executor creation: {agent_to_use.llm}")
                    agent_to_use.create_agent_executor(tools=task.tools)
                    logger.debug(f"Agent executor created. Executor LLM: {agent_to_use.agent_executor.llm}")
                    
                agent_to_use.agent_executor.callbacks = [step_callback]
                # Patch the _ask_human_input method on the mixin class
                from crewai.agents.agent_builder.base_agent_executor_mixin import CrewAgentExecutorMixin
                CrewAgentExecutorMixin._ask_human_input = staticmethod(partial(human_input_handler, execution_id=execution.id))
                
                #logger.debug(f"Set task index to {task_index} before executing task with description: {task.description}")
                
                # Execute task
                try:
                    if task.async_execution:
                        context = crew._get_context(task, [last_sync_output] if last_sync_output else [])
                        future = task.execute_async(agent=agent_to_use, context=context)
                        futures.append((task, future, task_index))
                    else:
                        if futures:
                            task_outputs = crew._process_async_tasks(futures)
                            futures.clear()
                        
                        context = crew._get_context(task, task_outputs)
                        #logger.debug(f"Executing task {task_index} with agent {agent_to_use.role}")
                        
                        # If this is a human input task, add the input to context
                        if task.human_input:
                            input_key = f"execution_{execution.id}_task_{task_index}_input"
                            
                            # First execution to get the prompt
                            initial_output = task.execute_sync(agent=agent_to_use, context=context)
                            #logger.debug(f"Initial execution complete, waiting for human input")
                            
                            # Wait for human input
                            human_response = cache.get(input_key)
                            while not human_response:
                                time.sleep(1)
                                human_response = cache.get(input_key)
                            
                            logger.debug(f"Received human input: {human_response}")
                            
                            # Make sure context is a dictionary
                            if isinstance(context, str):
                                new_context = {'input': context}
                            elif context is None:
                                new_context = {}
                            else:
                                new_context = context.copy()
                                
                            # Add input to context and execute again
                            new_context['human_input'] = human_response
                            new_context['input'] = human_response
                            #logger.debug(f"Context for second execution: {new_context}")
                            
                            task_output = task.execute_sync(agent=agent_to_use, context=new_context)
                            logger.debug(f"Second execution complete with input")
                        else:
                            # Non-human input task
                            task_output = task.execute_sync(agent=agent_to_use, context=context)
                        #logger.debug(f"Task execution complete. Output: {task_output}")
                        task_outputs = [task_output]
                        last_sync_output = task_output
                        
                        #logger.debug(f"Completed task {task_index}")
                except Exception as e:
                    logger.error(f"Error executing task {task_index}: {str(e)}")
                    raise
            
            if futures:
                task_outputs = crew._process_async_tasks(futures)
            
            return crew._create_crew_output(task_outputs)
            
        # Replace the original _execute_tasks method
        crew._execute_tasks = execute_tasks_with_tracking
        
        # Set callbacks on crew
        crew.step_callback = step_callback
        crew.task_callback = task_callback
        
        for agent in crew.agents:
            if not hasattr(agent, 'backstory') or agent.backstory is None:
                logger.warning(f"Agent {agent.role} has no backstory!")
                continue

            try:
                # Store original backstory
                original_backstory = agent.backstory
                # Clean and update the backstory
                cleaned_backstory = clean_text(original_backstory,"backstory")
                agent.backstory = cleaned_backstory
                agent._original_backstory = cleaned_backstory  

            except Exception as e:
                logger.error(f"Error cleaning backstory for {agent.role}: {str(e)}")
                # Fallback to simple escaping if cleaning fails
                agent.backstory = original_backstory.replace("{", "{{").replace("}", "}}")
                agent._original_backstory = agent.backstory
                
        # Clean expected_output for each task
        for task in crew.tasks:
            if hasattr(task, 'expected_output') and task.expected_output:
                original_expected_output = task.expected_output
                cleaned_expected_output = clean_text(original_expected_output, "expected_output")
                task.expected_output = cleaned_expected_output
                # Store the original for reference if needed
                task._original_expected_output = cleaned_expected_output
                
        # Sanitize inputs
        sanitized_inputs = {}
        for k, v in inputs.items():
            # Handle string values
            if isinstance(v, str):
                sanitized_inputs[k] = v.strip()
            # For dictionary values, pass through directly
            elif isinstance(v, dict):
                # Keep the original data for the actual crew inputs without any redaction
                sanitized_inputs[k] = v
            # Keep other values as is
            else:
                sanitized_inputs[k] = v
                
        # Add some debugging information
        logger.debug(f"Prepared {len(sanitized_inputs)} input parameters for crew execution")
        logger.debug(f"Input keys: {', '.join(sanitized_inputs.keys())}")
        
        # Run the crew based on process type
        if execution.crew.process == 'sequential':
            logger.debug("Starting sequential crew execution")
            result = crew.kickoff(inputs=sanitized_inputs)
        elif execution.crew.process == 'hierarchical':
            logger.debug("Starting hierarchical crew execution")
            result = crew.kickoff(inputs=sanitized_inputs)
        elif execution.crew.process == 'for_each':
            logger.debug("Starting for_each crew execution")
            inputs_array = sanitized_inputs.get('inputs_array', [])
            result = crew.kickoff_for_each(inputs=inputs_array)
        elif execution.crew.process == 'async':
            logger.debug("Starting async crew execution")
            result = crew.kickoff_async(inputs=sanitized_inputs)
        elif execution.crew.process == 'for_each_async':
            logger.debug("Starting for_each_async crew execution")
            inputs_array = sanitized_inputs.get('inputs_array', [])
            result = crew.kickoff_for_each_async(inputs=inputs_array)
        else:
            raise ValueError(f"Unknown process type: {execution.crew.process}")
            
        # Create completion stage
        ExecutionStage.objects.create(
            execution=execution,
            stage_type='task_completion',
            title='Execution Complete',
            content=f'Completed all tasks for crew {crew.name}',
            status='completed'
        )
        
        # Store result in CrewOutput
        crew_output = CrewOutput.objects.create(
            raw=str(result),
            json_dict=result if isinstance(result, dict) else None
        )
        
        # Update execution with output
        execution.crew_output = crew_output
        execution.save()
        logger.debug(f"Crew output: {result}")
        return result
        
    except Exception as e:
        # Create error stage
        ExecutionStage.objects.create(
            execution=execution,
            stage_type='task_error',
            title='Execution Error',
            content=str(e),
            status='error'
        )
        raise 


def handle_execution_error(execution, exception, task_id=None):
    logger.error(f"Error during crew execution: {str(exception)}", exc_info=True)
    update_execution_status(execution, 'FAILED')
    error_message = f"Crew execution failed: {str(exception)}"
    log_crew_message(execution, error_message, agent=None)
    execution.error_message = error_message
    execution.save()

    # Print the full traceback to stdout
    print("Full traceback:")
    traceback.print_exc()

def save_result_to_file(execution, result):
    """
    Save crew execution result to cloud storage using PathManager.
    
    Args:
        execution: The execution instance
        result: The result to save
    """
    try:
        # Generate the file name with timestamp
        timestamp = datetime.now().strftime("%y-%m-%d-%H-%M")
        crew_name = execution.crew.name.replace(' ', '_')
        
        # Get client name if available, otherwise use a default
        client_name = 'no_client'
        if execution.client_id:
            try:
                client = Client.objects.get(id=execution.client_id)
                if client.status == 'active':  # Check if client is active
                    client_name = client.name.replace(' ', '_')
                    logger.info(f"Using client name: {client_name} for output file")
                else:
                    logger.warning(f"Client {client.name} is not active (status: {client.status})")
            except Client.DoesNotExist:
                logger.warning(f"Client with ID {execution.client_id} not found")
            
        file_name = f"{client_name}-finaloutput_{timestamp}.txt"
        
        # Create relative path for the file
        relative_path = os.path.join(
            'crew_runs',
            crew_name,
            file_name
        )
        
        # Initialize PathManager with user ID
        path_manager = PathManager(user_id=execution.user.id)
        
        # Convert content to string and create a ContentFile
        content = str(result)
        file_obj = ContentFile(content.encode('utf-8'))
        file_obj.name = file_name
        
        # Save the file using PathManager
        saved_path = path_manager.save_file(file_obj, relative_path)
        
        # Log the file creation
        log_message = f"Final output saved to: {saved_path}"
        log_crew_message(execution, log_message, agent="System")
        logger.info(log_message)
        
        return saved_path
        
    except Exception as e:
        error_message = f"Error saving crew result file: {str(e)}"
        logger.error(error_message)
        log_crew_message(execution, error_message, agent="System")
        raise

@shared_task(bind=True)
def execute_crew(self, execution_id, organization_id=None):
    """Execute a crew with the given execution ID"""
    try:
        # Set organization context if provided
        from apps.organizations.utils import OrganizationContext
        from contextlib import nullcontext
        
        # If organization_id is not provided, try to get it from the execution object first
        if not organization_id:
            try:
                # Use unfiltered_objects to avoid organization filtering when fetching initial object
                from apps.agents.models import CrewExecution
                execution_obj = CrewExecution.unfiltered_objects.get(id=execution_id)
                organization_id = execution_obj.organization_id
            except Exception as e:
                logger.warning(f"Could not determine organization for execution {execution_id}: {str(e)}")
        
        # Use organization context manager if we have an organization ID
        context_manager = OrganizationContext.organization_context(organization_id) if organization_id else nullcontext()
        
        with context_manager:
            execution = CrewExecution.objects.get(id=execution_id)
            #logger.debug(f"Attempting to start crew execution for id: {execution_id} (task_id: {self.request.id})")
            
            # Save the Celery task ID
            execution.task_id = self.request.id
            execution.save()
            
            # Create initial stage
            ExecutionStage.objects.create(
                execution=execution,
                stage_type='task_start',
                title='Starting Execution',
                content=f'Starting execution for crew: {execution.crew.name}',
                status='completed'
            )
            
            # Update execution status to PENDING with task_index 0
            update_execution_status(execution, 'PENDING', task_index=0)
            
            logger.debug(f"Starting crew execution for id: {execution_id} (task_id: {self.request.id})")
            
            # Initialize crew
            crew = initialize_crew(execution)
            if not crew:
                raise ValueError("Failed to initialize crew")
            
            # Run crew
            result = run_crew(self.request.id, crew, execution)
            
            # Save the result and update execution status to COMPLETED
            if result:
                #log_crew_message(execution, str(result), agent='System')
                save_result_to_file(execution, result)
                pass

            # Use the last task index when setting completed status
            last_task_index = len(crew.tasks) - 1 if crew and crew.tasks else None
            update_execution_status(execution, 'COMPLETED', task_index=last_task_index)
            
            return execution.id
            
    except Exception as e:
        logger.error(f"Error during crew execution: {str(e)}")
        if 'execution' in locals():
            handle_execution_error(execution, e, task_id=getattr(self, 'request', None) and self.request.id)
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise 
