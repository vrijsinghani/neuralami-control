from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from apps.common.utils import get_models
from pydantic import BaseModel
import os
import importlib
import logging
import uuid
import random
import json
from django.contrib.postgres.fields import ArrayField
from django.conf import settings
from apps.agents.utils import load_tool, get_tool_description
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
from django.utils import timezone
import re
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from core.storage import SecureFileStorage

logger = logging.getLogger(__name__)

User = get_user_model()

import glob

def get_agent_avatars():
    # Get the default avatar list
    default_avatars = [
        'team-5.jpg', 'team-4.jpg', 'team-3.jpg', 'team-2.jpg', 'kal-visuals-square.jpg',
        'team-1.jpg', 'marie.jpg', 'ivana-squares.jpg', 'ivana-square.jpg'
    ]
    
    # Get additional avatars from static directory
    static_path = os.path.join('static', 'assets', 'img', 'agent-avatar*')
    additional_avatars = [os.path.basename(f) for f in glob.glob(static_path)]
    
    return default_avatars + additional_avatars

AVATAR_CHOICES = get_agent_avatars()

def random_avatar():
    return random.choice(AVATAR_CHOICES)

def get_available_tools():
    tools_dir = os.path.join('apps', 'agents', 'tools')
    available_tools = []

    for root, dirs, files in os.walk(tools_dir):
        for dir_name in dirs:
            if not dir_name.startswith('__'):  # Exclude directories like __pycache__
                tool_path = os.path.relpath(os.path.join(root, dir_name), tools_dir)
                available_tools.append(tool_path.replace(os.path.sep, '.'))

    return available_tools

def default_embedder():
    return {'provider': 'openai'}

# Create storage for agent task files
task_output_storage = SecureFileStorage(
    private=True,
    collection='agent_task_outputs'
)

def user_directory_path(instance, filename):
    # Return only the filename since the collection is handled by SecureFileStorage
    return filename

class Tool(models.Model):
    tool_class = models.CharField(max_length=255)
    tool_subclass = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    module_path = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.module_path:
            self.module_path = f"apps.agents.tools.{self.tool_class}"
        
        try:
            tool = load_tool(self)
            if tool:
                self.name = getattr(tool, 'name', self.tool_subclass)
                self.description = get_tool_description(tool.__class__)
            else:
                raise ValueError(f"Failed to load tool: {self.module_path}.{self.tool_subclass}. Check the logs for more details.")
        except Exception as e:
            logger.error(f"Error in Tool.save: {str(e)}")
            raise ValidationError(f"Error loading tool: {str(e)}")

        super().save(*args, **kwargs)

class ToolRun(models.Model):
    """Model to track tool executions"""
    TOOL_RUN_STATUS = (
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )
    
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE)
    conversation = models.ForeignKey('Conversation', on_delete=models.CASCADE, related_name='tool_runs', null=True, blank=True)
    message = models.ForeignKey('ChatMessage', on_delete=models.CASCADE, related_name='tool_runs', null=True, blank=True)
    status = models.CharField(max_length=20, choices=TOOL_RUN_STATUS, default='pending')
    inputs = models.JSONField()
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tool.name} - {self.status} ({self.created_at})"

class Agent(models.Model):
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=100)
    goal = models.TextField()
    backstory = models.TextField()
    llm = models.CharField(max_length=100, default=settings.GENERAL_MODEL)
    tools = models.ManyToManyField(Tool, blank=True)
    function_calling_llm = models.CharField(max_length=100, null=True, blank=True, default=settings.GENERAL_MODEL)
    max_iter = models.IntegerField(default=25)
    max_rpm = models.IntegerField(null=True, blank=True)
    max_execution_time = models.IntegerField(null=True, blank=True)
    verbose = models.BooleanField(default=False)
    allow_delegation = models.BooleanField(default=False)
    step_callback = models.CharField(max_length=255, null=True, blank=True)
    cache = models.BooleanField(default=True)
    system_template = models.TextField(null=True, blank=True)
    prompt_template = models.TextField(null=True, blank=True)
    response_template = models.TextField(null=True, blank=True)
    allow_code_execution = models.BooleanField(default=False)
    max_retry_limit = models.IntegerField(default=2)
    use_system_prompt = models.BooleanField(default=True)
    respect_context_window = models.BooleanField(default=True)
    avatar = models.CharField(max_length=100, default=random_avatar)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        available_models = get_models()
        if self.llm not in available_models:
            raise ValidationError({'llm': f"Selected LLM '{self.llm}' is not available. Please choose from: {', '.join(available_models)}"})

    def get_tool_settings(self, tool):
        """Get settings for a specific tool."""
        return self.tool_settings.filter(tool=tool).first()

    def get_forced_output_tools(self):
        """Get all tools that have force_output_as_result=True."""
        return self.tools.filter(
            id__in=self.tool_settings.filter(
                force_output_as_result=True
            ).values_list('tool_id', flat=True)
        )

    def has_force_output_enabled(self, tool):
        """Check if force output is enabled for a specific tool."""
        tool_setting = self.tool_settings.filter(tool=tool).first()
        return tool_setting.force_output_as_result if tool_setting else False

class Task(models.Model):
    description = models.TextField()
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True)
    expected_output = models.TextField()
    tools = models.ManyToManyField(Tool, blank=True)
    async_execution = models.BooleanField(default=False)
    context = models.ManyToManyField('self', symmetrical=False, blank=True)
    config = models.JSONField(null=True, blank=True)
    output_json = models.CharField(max_length=255, null=True, blank=True)
    output_pydantic = models.CharField(max_length=255, null=True, blank=True)
    output_file = models.CharField(max_length=255, null=True, blank=True)
    output = models.TextField(null=True, blank=True)
    callback = models.CharField(max_length=255, null=True, blank=True)
    human_input = models.BooleanField(default=False)
    converter_cls = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.description[:50]

    def save_output_file(self, content):
        if self.output_file:
            file_name = os.path.basename(self.output_file)
        else:
            file_name = f"task_{self.id}_output.txt"
        
        try:
            # Create a ContentFile with the content
            content_file = ContentFile(content)
            
            # Save using our secure storage
            file_path = task_output_storage.save(file_name, content_file)
            
            # Update the model's output_file field
            self.output_file = file_path
            self.save()
        except Exception as e:
            logger.error(f"Error saving output file for task {self.id}: {e}")
            raise

class Crew(models.Model):
    name = models.CharField(max_length=100)
    agents = models.ManyToManyField(Agent)
    tasks = models.ManyToManyField(Task, through='CrewTask')
    process = models.CharField(max_length=20, choices=[('sequential', 'Sequential'), ('hierarchical', 'Hierarchical')], default='sequential')
    verbose = models.BooleanField(default=False)
    manager_llm = models.CharField(max_length=100, null=True, blank=True, default=settings.GENERAL_MODEL)
    function_calling_llm = models.CharField(max_length=100, null=True, blank=True, default=settings.GENERAL_MODEL)
    config = models.JSONField(null=True, blank=True)
    max_rpm = models.IntegerField(null=True, blank=True)
    language = models.CharField(max_length=50, default='English')
    language_file = models.CharField(max_length=255, null=True, blank=True)
    memory = models.BooleanField(default=False)
    cache = models.BooleanField(default=True)
    embedder = models.JSONField(default=default_embedder)
    full_output = models.BooleanField(default=False)
    share_crew = models.BooleanField(default=False)
    output_log_file = models.CharField(max_length=255, null=True, blank=True)
    manager_agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_crews')
    manager_callbacks = models.JSONField(null=True, blank=True)
    prompt_file = models.CharField(max_length=255, null=True, blank=True)
    planning = models.BooleanField(default=False)
    planning_llm = models.CharField(max_length=100, null=True, blank=True, default=settings.GENERAL_MODEL)
    input_variables = models.JSONField(null=True, blank=True, default=list)

    def __str__(self):
        return self.name

class CrewExecution(models.Model):
    """Represents a single execution of a crew"""
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.ForeignKey('seo_manager.Client', on_delete=models.CASCADE, null=True)
    status = models.CharField(max_length=50, default='PENDING')
    task_id = models.CharField(max_length=50, null=True)
    inputs = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    conversation = models.ForeignKey('Conversation', on_delete=models.SET_NULL, null=True, related_name='crew_executions')
    crew_output = models.OneToOneField('CrewOutput', on_delete=models.SET_NULL, null=True, blank=True, related_name='crew_execution')
    human_input_request = models.JSONField(null=True, blank=True)
    human_input_response = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    chat_enabled = models.BooleanField(default=False)

    def get_conversation_history(self):
        """Get formatted conversation history including messages and tool results"""
        if not self.conversation:
            return []
            
        messages = ChatMessage.objects.filter(
            conversation=self.conversation,
            is_deleted=False
        ).order_by('timestamp')
        
        # Use the formatted_message property for each message
        return [msg.formatted_message for msg in messages]

    def __str__(self):
        return f"{self.crew.name} - {self.status} ({self.created_at})"

    def save_task_output_file(self, task, content):
        task.save_output_file(content)

class CrewMessage(models.Model):
    execution = models.ForeignKey(CrewExecution, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    agent = models.CharField(max_length=255, null=True, blank=True)
    crewai_task_id = models.IntegerField(null=True, blank=True)  # For kanban board placement

    def __str__(self):
        return f"{self.timestamp}: {self.content[:50]}"

class CrewOutput(models.Model):
    raw = models.TextField()
    pydantic = models.JSONField(null=True, blank=True)
    json_dict = models.JSONField(null=True, blank=True)
    token_usage = models.JSONField(null=True, blank=True)

    @property
    def json(self):
        return json.dumps(self.json_dict) if self.json_dict else None

    def to_dict(self):
        return self.json_dict or (self.pydantic.dict() if self.pydantic else None) or {}

    def __str__(self):
        if self.pydantic:
            return str(self.pydantic)
        elif self.json_dict:
            return json.dumps(self.json_dict)
        else:
            return self.raw

    def save(self, *args, **kwargs):
        # Convert UsageMetrics to a dictionary if it's not already
        if self.token_usage and hasattr(self.token_usage, 'dict'):
            self.token_usage = self.token_usage.dict()
        super().save(*args, **kwargs)

class CrewTask(models.Model):
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, related_name='crew_tasks')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = ('crew', 'task')

    def __str__(self):
        return f"{self.crew.name} - {self.task.description} (Order: {self.order})"

class AgentToolSettings(models.Model):
    agent = models.ForeignKey('Agent', on_delete=models.CASCADE, related_name='tool_settings')
    tool = models.ForeignKey('Tool', on_delete=models.CASCADE)
    force_output_as_result = models.BooleanField(default=False)

    class Meta:
        unique_together = ('agent', 'tool')

class SlackChannelClientMapping(models.Model):
    """Map Slack channels to clients for automatic client identification"""
    channel_id = models.CharField(max_length=32)
    team_id = models.CharField(max_length=32)
    client = models.ForeignKey('seo_manager.Client', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('channel_id', 'team_id')
        db_table = 'slack_channel_client_mappings'

    def __str__(self):
        return f"Slack Channel {self.channel_id} -> Client {self.client_id}"

class ExecutionStage(models.Model):
    STAGE_TYPES = [
        ('task_start', 'Task Start'),
        ('thinking', 'Thinking'),
        ('tool_usage', 'Tool Usage'),
        ('tool_results', 'Tool Results'),
        ('human_input', 'Human Input'),
        ('completion', 'Completion')
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ]
    
    execution = models.ForeignKey(CrewExecution, on_delete=models.CASCADE, related_name='stages')
    stage_type = models.CharField(max_length=20, choices=STAGE_TYPES)
    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    crewai_task_id = models.IntegerField(null=True, blank=True)  # For kanban board placement
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = 'Execution Stage'
        verbose_name_plural = 'Execution Stages'
    
    def __str__(self):
        return f"{self.get_stage_type_display()} - {self.title}"

class Conversation(models.Model):
    session_id = models.UUIDField(unique=True)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    agent = models.ForeignKey('Agent', on_delete=models.SET_NULL, null=True)
    client = models.ForeignKey('seo_manager.Client', on_delete=models.SET_NULL, null=True)
    participant_type = models.CharField(
        max_length=50, 
        choices=[
            ('agent', 'Agent Chat'),
            ('crew', 'Crew Chat')
        ],
        default='agent'
    )
    crew_execution = models.ForeignKey(
        'CrewExecution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_conversations'
    )
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.session_id})"

    async def get_recent_messages(self, limit=10):
        """Get recent messages for this conversation"""
        return await self.chatmessage_set.filter(
            is_deleted=False
        ).order_by('-timestamp')[:limit]

    async def get_task_outputs(self, limit=5):
        """Get recent task outputs from crew execution"""
        if self.crew_execution and self.crew_execution.crew_output:
            return self.crew_execution.crew_output.to_dict()
        return None

class CrewChatSession(models.Model):
    conversation = models.OneToOneField(
        'Conversation',
        on_delete=models.CASCADE,
        related_name='crew_chat_session'
    )
    crew_execution = models.OneToOneField(
        'CrewExecution',
        on_delete=models.CASCADE,
        related_name='chat_session'
    )
    last_activity = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ('active', 'Active'),
            ('paused', 'Paused'),
            ('completed', 'Completed'),
            ('cleaned', 'Cleaned')
        ],
        default='active'
    )
    context_data = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=['last_activity', 'status'])
        ]

    def __str__(self):
        return f"Crew Chat Session - {self.conversation.title}"

    async def get_full_context(self):
        """Get full context including messages, task outputs, and context data"""
        messages = await self.conversation.get_recent_messages()
        task_outputs = await self.conversation.get_task_outputs()
        
        return {
            'messages': messages,
            'task_outputs': task_outputs,
            'context_data': self.context_data
        }

    def update_context(self, key, value):
        """Update a specific context value"""
        if self.context_data is None:
            self.context_data = {}
        self.context_data[key] = value
        self.save(update_fields=['context_data', 'last_activity'])

class ChatMessage(models.Model):
    """Model for storing chat messages."""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=255)
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_agent = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    model = models.CharField(max_length=255, default='unknown')
    task_id = models.IntegerField(null=True, blank=True)
    
    @property
    def formatted_message(self):
        """Get message with associated tool results"""
        base = {
            'type': 'agent_message' if self.is_agent else 'user_message',
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'model': self.model,
            'task_id': self.task_id
        }
        
        # Add tool results if any exist
        tool_runs = self.tool_runs.all()
        if tool_runs:
            base['tool_results'] = [
                {
                    'tool': run.tool.name,
                    'inputs': run.inputs,
                    'result': run.result,
                    'status': run.status
                }
                for run in tool_runs
            ]
            
        return base

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['conversation', 'timestamp']),
            models.Index(fields=['session_id']),
            models.Index(fields=['is_deleted']),  # Add index for is_deleted field
        ]

    def __str__(self):
        return f"{self.timestamp}: {'Agent' if self.is_agent else 'User'} - {self.content[:50]}..."

class TokenUsage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='token_usage')
    message = models.ForeignKey('ChatMessage', on_delete=models.SET_NULL, null=True, blank=True)
    tool_run = models.ForeignKey('ToolRun', on_delete=models.SET_NULL, null=True, blank=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    model = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # Changed from JSONField to models.JSONField

    class Meta:
        indexes = [
            models.Index(fields=['conversation', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.conversation_id} - {self.total_tokens} tokens"

class UserSlackIntegration(models.Model):
    """Store Slack integration details for users"""
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255)
    team_id = models.CharField(max_length=32)
    team_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_slack_integrations'

    def __str__(self):
        return f"{self.user.username} - {self.team_name}"

class Flow(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    crews = models.ManyToManyField('Crew', through='FlowCrew')
    state_schema = models.JSONField(help_text="JSON schema for flow state validation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class FlowCrew(models.Model):
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE)
    crew = models.ForeignKey('Crew', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    trigger_condition = models.TextField(blank=True, 
        help_text="Python condition for triggering this crew")

    class Meta:
        ordering = ['order']

class FlowExecution(models.Model):
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE)
    state = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='pending', 
        choices=(
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
