import json
from channels.generic.websocket import AsyncWebsocketConsumer
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import CrewExecution, CrewMessage, ChatMessage, Agent
from django.core.cache import cache
from apps.common.utils import format_message, get_llm
from .utils import get_tool_classes
import logging
import uuid
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, FunctionMessage, BaseMessage, messages_from_dict, messages_to_dict
import asyncio
import tiktoken
from langchain_community.chat_models import ChatLiteLLM
from langchain_core.tools import Tool
from django.utils import timezone
from apps.seo_manager.models import Client
from langchain.prompts import ChatPromptTemplate
from langchain.agents import initialize_agent, AgentType, AgentExecutor, create_structured_chat_agent
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain.agents.output_parsers import JSONAgentOutputParser
from langchain_core.callbacks import BaseCallbackHandler
import datetime
from langchain.tools import StructuredTool
from typing import Dict, Any, List
from pydantic import create_model
from langchain.memory import ConversationBufferMemory
from langchain_core.chat_history import BaseChatMessageHistory
import re
import time

logger = logging.getLogger(__name__)

def count_tokens(text):
    """Count tokens in text using tiktoken"""
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(encoding.encode(text))

class ConnectionTestConsumer(OrganizationAwareConsumer):
    async def connect(self):
        # Set organization context
        await super().connect()
        
        await self.accept()
        await self.send(text_data=json.dumps({
            'message': 'Connected to server'
        }))

    async def disconnect(self, close_code):
        # Clear organization context
        await super().disconnect(close_code)

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']

            # Echo the received message back to the client
            await self.send(text_data=json.dumps({
                'message': f'Server received: {message}'
            }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))
        except KeyError:
            await self.send(text_data=json.dumps({
                'error': 'Missing "message" key in JSON'
            }))

class CrewExecutionConsumer(OrganizationAwareConsumer):
    async def connect(self):
        # Set organization context first
        await super().connect()
        
        self.execution_id = self.scope['url_route']['kwargs']['execution_id']
        self.execution_group_name = f'crew_execution_{self.execution_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.execution_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial status
        await self.send_execution_status()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.execution_group_name,
            self.channel_name
        )
        
        # Clear organization context
        await super().disconnect(close_code)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'human_input':
            input_key = text_data_json.get('input_key')
            user_input = text_data_json.get('input')
            await self.handle_human_input(input_key, user_input)

    async def crew_execution_update(self, event):
        status = event.get('status', '')  # No formatting applied
        formatted_messages = [
            {
                'agent': msg.get('agent', 'System'),
                'content': format_message(msg.get('content', ''))
            } for msg in event.get('messages', []) if msg.get('content')
        ]
        # logger.info(f"Sending status: {status}")
        # logger.info(f"Sending formatted messages: {formatted_messages}")
        await self.send(text_data=json.dumps({
            'status': status,
            'messages': formatted_messages,
            'human_input_request': event.get('human_input_request')
        }))

    @database_sync_to_async
    def handle_human_input(self, input_key, user_input):
        cache.set(f"{input_key}_response", user_input, timeout=3600)
        execution = CrewExecution.objects.get(id=self.execution_id)
        CrewMessage.objects.create(
            execution=execution,
            agent='Human',
            content=f"Human input received: {user_input}"
        )

    @database_sync_to_async
    def get_execution_status(self):
        execution = CrewExecution.objects.get(id=self.execution_id)
        messages = CrewMessage.objects.filter(execution=execution).order_by('-timestamp')[:10]
        return {
            'status': execution.status,
            'messages': [{'agent': msg.agent, 'content': msg.content} for msg in messages],
        }

    async def send_execution_status(self):
        status_data = await self.get_execution_status()
        status = status_data['status']  # No formatting applied
        formatted_messages = [
            {
                'agent': msg['agent'],
                'content': format_message(msg['content'])
            } for msg in status_data['messages'] if msg.get('content')
        ]
        
        # logger.info(f"Sending status: {status}")
        # logger.info(f"Sending formatted messages: {formatted_messages}")
        
        await self.send(text_data=json.dumps({
            'status': status,
            'messages': formatted_messages,
        }))


