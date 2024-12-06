from django.views.generic import TemplateView
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from apps.agents.models import Agent, Conversation
from apps.common.utils import get_models
from django.conf import settings
from apps.seo_manager.models import Client
import logging
import uuid

logger = logging.getLogger(__name__)

@login_required
@require_POST
def delete_conversation(request, session_id):
    try:
        conversation = get_object_or_404(Conversation, session_id=session_id, user=request.user)
        conversation.delete()
        logger.info(f"Deleted conversation: {conversation.id}")
        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

class ChatView(LoginRequiredMixin, TemplateView):
    template_name = 'agents/chat.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            # Get session_id from URL parameters or generate new one
            session_id = self.kwargs.get('session_id', str(uuid.uuid4()))
            logger.info(f"Using chat session ID: {session_id}")
            
            # Get base queryset for conversations
            conversations_qs = Conversation.objects.filter(
                user=self.request.user,
                is_active=True
            ).select_related('agent', 'client').order_by('-updated_at')
            
            # Get current conversation if exists
            current_conversation = None
            if 'session_id' in self.kwargs:
                try:
                    current_conversation = conversations_qs.get(session_id=session_id)
                    logger.info(f"Found existing conversation: {current_conversation}")
                except Conversation.DoesNotExist:
                    logger.warning(f"No conversation found for session_id: {session_id}")
            
            # Get recent conversations (limited to 50)
            conversations = conversations_qs[:50]
            logger.info(f"Found {conversations.count()} conversations")
            
            # Get all agents
            agents = Agent.objects.all().order_by('name')
            logger.info(f"Found {agents.count()} agents")
            
            # Get all clients
            clients = Client.objects.all().order_by('name')
            logger.info(f"Found {clients.count()} clients")
            
            # Get models list
            models = get_models()
            logger.info(f"Found {len(models)} models")
            
            # Get default model
            default_model = settings.GENERAL_MODEL
            logger.info(f"Using default model: {default_model}")
            
            context.update({
                'agents': agents,
                'clients': clients,
                'models': models,
                'conversations': conversations,
                'current_conversation': current_conversation,
                'add_agent_url': reverse('agents:add_agent'),
                'segment': 'chat',
                'default_model': default_model,
                'session_id': session_id,
            })
            logger.info("Context prepared successfully")
            
        except Exception as e:
            logger.error(f"Error preparing chat view context: {str(e)}", exc_info=True)
            raise
            
        return context