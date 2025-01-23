from django.http import HttpResponse
import csv
from django.views import View

class ExportConversationView(View):
    def get(self, request, conversation_id):
        try:
            # Get conversation messages
            messages = Message.objects.filter(conversation_id=conversation_id).order_by('created_at')
            
            # Create the HttpResponse object with CSV header
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="conversation_{conversation_id}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Timestamp', 'Role', 'Content'])
            
            # Write messages
            for message in messages:
                writer.writerow([
                    message.created_at,
                    message.role,
                    message.content
                ])
            
            return response
            
        except Exception as e:
            logger.error(f"Error exporting conversation {conversation_id}: {str(e)}")
            return HttpResponse(status=500) 