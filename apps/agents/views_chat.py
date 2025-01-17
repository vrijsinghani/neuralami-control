from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from apps.agents.models import Agent, Conversation, Crew
from apps.seo_manager.models import Client
from apps.common.utils import get_models
import logging
import uuid

logger = logging.getLogger(__name__)

@login_required
def chat_view(request, session_id=None):
    """Chat interface view"""
    try:
        # Create new session if none provided
        if not session_id:
            session_id = str(uuid.uuid4())
            
        # Get existing conversation or None
        conversation = None
        if session_id:
            conversation = Conversation.objects.filter(
                session_id=session_id,
                user=request.user
            ).first()
            
        # Get all conversations for sidebar
        conversations = Conversation.objects.filter(
            user=request.user
        ).order_by('-updated_at')
        
        # Get available agents and crews
        agents = Agent.objects.all()
        crews = Crew.objects.all()
        
        # Get available clients
        clients = Client.objects.all()
        
        # Get available models
        models = get_models()
        default_model = models[0] if models else None
        
        context = {
            'session_id': session_id,
            'current_conversation': conversation,
            'conversations': conversations,
            'agents': agents,
            'crews': crews,
            'clients': clients,
            'models': models,
            'default_model': default_model
        }
        
        return render(request, 'agents/chat.html', context)
        
    except Exception as e:
        logger.error(f"Error in chat view: {str(e)}")
        raise

@login_required
@require_http_methods(["DELETE"])
def delete_conversation(request, session_id):
    """Delete a conversation"""
    try:
        conversation = Conversation.objects.get(
            session_id=session_id,
            user=request.user
        )
        conversation.delete()
        return JsonResponse({'status': 'success'})
    except Conversation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Conversation not found'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)