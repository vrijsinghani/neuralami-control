from django.urls import path
from .views import ExportConversationView

urlpatterns = [
    path('conversations/<int:conversation_id>/export/', 
         ExportConversationView.as_view(), 
         name='export_conversation'),
] 