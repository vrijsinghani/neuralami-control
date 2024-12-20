from django.core.management.base import BaseCommand
from django.db import transaction
from apps.agents.models import Conversation, ChatMessage, ToolRun, TokenUsage
from django.core.cache import cache

class Command(BaseCommand):
    help = 'Clears all conversations and their related data (messages, tool runs, token usage) from database and cache'

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                # Get counts of conversation-related data before deletion
                conversations = Conversation.objects.all()
                conv_count = conversations.count()
                msg_count = ChatMessage.objects.filter(conversation__in=conversations).count()
                tool_run_count = ToolRun.objects.filter(conversation__in=conversations).count()
                token_usage_count = TokenUsage.objects.filter(conversation__in=conversations).count()
                
                # Delete conversations which will cascade delete related data
                # due to foreign key relationships with on_delete=CASCADE
                conversations.delete()
                
                # Clear the Django cache (which stores message history)
                cache.clear()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully deleted:\n'
                        f'- {conv_count} conversations\n'
                        f'- {msg_count} messages\n'
                        f'- {tool_run_count} tool runs\n'
                        f'- {token_usage_count} token usage records\n'
                        f'Cache cleared.'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error clearing chat data: {str(e)}'
                )
            ) 