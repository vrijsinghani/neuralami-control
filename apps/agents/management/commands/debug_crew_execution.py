from django.core.management.base import BaseCommand
import logging
from apps.agents.models import Crew, Agent, Task, CrewExecution
from apps.agents.tasks import execute_crew
from crewai import Crew as CrewAI
from crewai import Agent as CrewAgent
from crewai import Task as CrewAITask

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Debug crew execution'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting crew creation and execution debug test")
        agents = self.create_test_agents()
        tasks = self.create_test_tasks()
        crew = self.create_crew(agents, tasks)

        if crew:
            self.execute_test_crew(crew)

    def create_test_agents(self):
        agents = [
            CrewAgent(role="Web Crawler", goal="Extract relevant information from web pages", backstory="You are a web crawler tasked with gathering data from various online sources to support research and analysis."),
        ]
        logger.debug(f"Created agents: {agents}")
        return agents

    def create_test_tasks(self):
        tasks = [
            CrewAITask(description="Crawl specified websites to extract its contents.", expected_output="A marked down file of the contents of a website"),
        ]
        logger.debug(f"Created tasks: {tasks}")
        return tasks

    def create_crew(self, agents, tasks) -> CrewAI:
        try:
            crew = CrewAI(
                agents=agents,
                tasks=tasks,
                process='sequential',
                verbose=True,
                manager_llm='gpt-4o-mini',
                function_calling_llm='gpt-4o-mini',
                language='English',
            )
            logger.debug(f"Crew created successfully: {crew}")
            return crew
        except Exception as e:
            logger.error(f"Error creating crew: {e}")
            return None

    def execute_test_crew(self, crew):
        try:
            execution = CrewExecution(crew=crew, user=None)
            execution.save()
            execute_crew.delay(execution.id)
            logger.debug(f"Crew execution started for execution ID: {execution.id}")
        except Exception as e:
            logger.error(f"Error executing crew: {e}")
