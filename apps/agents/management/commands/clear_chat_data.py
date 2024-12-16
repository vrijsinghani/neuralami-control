from django.core.management.base import BaseCommand
from django.db import transaction
from apps.agents.models import Conversation, ChatMessage
from django.core.cache import cache

class Command(BaseCommand):
    help = 'Clears all conversation and message data from database and cache'

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                # Get counts before deletion
                conv_count = Conversation.objects.count()
                msg_count = ChatMessage.objects.count()
                
                # Delete all messages first
                ChatMessage.objects.all().delete()
                
                # Then delete all conversations
                Conversation.objects.all().delete()
                
                # Clear the Django cache (which stores message history)
                cache.clear()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully deleted {conv_count} conversations and {msg_count} messages. Cache cleared.'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error clearing chat data: {str(e)}'
                )
            ) 