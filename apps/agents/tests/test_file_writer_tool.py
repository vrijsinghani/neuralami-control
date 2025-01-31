import os
import sys
import logging
import json
from unittest.mock import patch, MagicMock
from functools import wraps
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai.agents.crew_agent_executor import CrewAgentExecutor
from apps.agents.tools.file_writer_tool.file_writer_tool import FileWriterTool
from apps.agents.tools.file_read_tool.file_read_tool import FileReadTool

# Load environment variables first
load_dotenv()

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(project_root)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

# Reset to default OpenAI API and clear proxy token
os.environ['OPENAI_API_BASE'] = 'https://api.openai.com/v1'
os.environ['LITELLM_MASTER_KEY'] = ''

# Configure logging
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for maximum verbosity
logger = logging.getLogger(__name__)

def debug_crew_executor(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Get the instance (self) from args
            instance = args[0] if args else None
            
            # Log entry point
            logger.debug(f"→ Entering {func.__name__}")
            
            # Special logging for specific methods
            if func.__name__ == '_format_answer':
                logger.debug(f"Raw answer to parse: {args[1]}")  # args[1] is the answer string
            elif func.__name__ == '_execute_tool_and_check_finality':
                agent_action = args[1]  # args[1] is AgentAction
                logger.debug(f"Tool to execute: {agent_action.tool}")
                logger.debug(f"Tool input (raw): {repr(agent_action.tool_input)}")
                logger.debug(f"Tool input (type): {type(agent_action.tool_input)}")
            
            result = func(*args, **kwargs)
            
            # Special logging for results
            if func.__name__ == '_format_answer':
                logger.debug(f"Parsed result type: {type(result)}")
                if hasattr(result, 'tool_input'):
                    logger.debug(f"Parsed tool_input: {repr(result.tool_input)}")
            elif func.__name__ == '_execute_tool_and_check_finality':
                logger.debug(f"Tool execution result: {result}")
            
            return result
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper

def create_file_handling_crew():
    # Patch the critical methods in CrewAgentExecutor
    patches = [
        patch('crewai.agents.crew_agent_executor.CrewAgentExecutor._format_answer'),
        patch('crewai.agents.crew_agent_executor.CrewAgentExecutor._execute_tool_and_check_finality'),
        patch('crewai.agents.crew_agent_executor.CrewAgentParser.parse'),
        patch('crewai.agents.crew_agent_executor.ToolUsage.parse'),
        patch('crewai.agents.crew_agent_executor.ToolUsage.use')
    ]
    
    with patch.multiple('crewai.agents.crew_agent_executor.CrewAgentExecutor',
                       _format_answer=debug_crew_executor(CrewAgentExecutor._format_answer),
                       _execute_tool_and_check_finality=debug_crew_executor(CrewAgentExecutor._execute_tool_and_check_finality)):
        
        # Initialize tools
        file_reader = FileReadTool()
        file_writer = FileWriterTool()
        
        # Create the agent with both tools
        file_handler_agent = Agent(
            role="File Handler",
            goal="Read and write files accurately",
            backstory="I am a specialized agent that handles file operations with precision and care.",
            tools=[file_reader, file_writer],
            verbose=True
        )

        # Create tasks (keep existing task definitions)
        read_task = Task(
            description="Read the content of the file '{input_file}'",
            expected_output="The complete content of the {input_file} file",
            agent=file_handler_agent,
        )

        write_task = Task(
            description="Write the content to a new file named '{output_file}'",
            expected_output="Confirmation that the file was written successfully",
            agent=file_handler_agent,
        )

        # Create the crew
        crew = Crew(
            agents=[file_handler_agent],
            tasks=[read_task, write_task],
            process=Process.sequential,
            verbose=True
        )

        try:
            result = crew.kickoff(
                inputs={
                    "input_file": "fluffy.txt",
                    "output_file": "fluffy1.txt",
                    "user_id": 1
                }
            )
            logger.info("File operations completed successfully")
            return result
        except Exception as e:
            logger.error(f"Error during file operations: {str(e)}", exc_info=True)
            raise

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set specific loggers to DEBUG
    logging.getLogger('crewai.agents.crew_agent_executor').setLevel(logging.DEBUG)
    logging.getLogger('crewai.agents.agent_executor').setLevel(logging.DEBUG)
    
    result = create_file_handling_crew()
    print("\nResult:", result)