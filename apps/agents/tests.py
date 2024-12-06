from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Crew, CrewExecution, CrewMessage
from .tasks import execute_crew, resume_crew_execution
from unittest.mock import patch

User = get_user_model()

class CrewExecutionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.crew = Crew.objects.create(name='Test Crew', process='sequential')
        self.execution = CrewExecution.objects.create(
            crew=self.crew,
            user=self.user,
            inputs={'test_input': 'value'}
        )

    @patch('apps.agents.tasks.run_crew')
    def test_execute_crew(self, mock_run_crew):
        mock_run_crew.return_value = {'test_output': 'result'}
        
        execute_crew(self.execution.id)
        
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, 'COMPLETED')
        self.assertEqual(self.execution.outputs, {'test_output': 'result'})

    @patch('apps.agents.tasks.run_crew')
    def test_execute_crew_human_input_required(self, mock_run_crew):
        from .tasks import HumanInputRequired
        mock_run_crew.side_effect = HumanInputRequired('Test human input required')
        
        execute_crew(self.execution.id)
        
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, 'WAITING_FOR_HUMAN_INPUT')
        self.assertEqual(self.execution.human_input_request, 'Test human input required')

    @patch('apps.agents.tasks.run_crew')
    def test_resume_crew_execution(self, mock_run_crew):
        mock_run_crew.return_value = {'test_output': 'result after human input'}
        
        self.execution.status = 'WAITING_FOR_HUMAN_INPUT'
        self.execution.human_input_response = 'Test human input'
        self.execution.save()
        
        resume_crew_execution(self.execution.id)
        
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, 'COMPLETED')
        self.assertEqual(self.execution.outputs, {'test_output': 'result after human input'})

    def test_crew_message_creation(self):
        CrewMessage.objects.create(
            execution=self.execution,
            content='Test message'
        )
        
        self.assertEqual(CrewMessage.objects.count(), 1)
        self.assertEqual(CrewMessage.objects.first().content, 'Test message')
