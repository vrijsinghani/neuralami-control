from django.core.management.base import BaseCommand
from apps.agents.models import ChatMessage, Conversation

class Command(BaseCommand):
    help = 'Check chat messages for a session'

    def add_arguments(self, parser):
        parser.add_argument('session_id', type=str)

    def handle(self, *args, **options):
        session_id = options['session_id']
        
        # Get conversation
        conversation = Conversation.objects.filter(session_id=session_id).first()
        if conversation:
            self.stdout.write(f"Found conversation: {conversation}")
        else:
            self.stdout.write(self.style.ERROR(f"No conversation found for session {session_id}"))
            return

        # Get messages
        messages = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')
        self.stdout.write(f"Found {messages.count()} messages")
        
        for msg in messages:
            self.stdout.write(f"""
Message:
- Content: {msg.content}
- Is Agent: {msg.is_agent}
- User: {msg.user}
- Agent: {msg.agent}
- Model: {msg.model}
- Timestamp: {msg.timestamp}
""") 