from django.core.management.base import BaseCommand
from apps.agents.models import CrewExecution
from apps.agents.tasks import run_crew

class Command(BaseCommand):
    help = 'Replay a crew execution from a specific task'

    def add_arguments(self, parser):
        parser.add_argument('execution_id', type=int, help='The ID of the CrewExecution to replay')
        parser.add_argument('-t', '--task_id', type=str, help='The ID of the task to start from')

    def handle(self, *args, **options):
        execution_id = options['execution_id']
        task_id = options['task_id']

        try:
            execution = CrewExecution.objects.get(id=execution_id)
            result = run_crew(execution, start_from_task=task_id)
            self.stdout.write(self.style.SUCCESS(f'Replay completed. Result: {result}'))
        except CrewExecution.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'CrewExecution with id {execution_id} does not exist'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during replay: {str(e)}'))