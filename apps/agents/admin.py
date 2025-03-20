from django.contrib import admin
from .models import (
    Crew, CrewExecution, CrewMessage, Agent, Task, Tool, CrewTask, SlackChannelClientMapping,
    ToolRun, AgentToolSettings, ExecutionStage, Conversation, CrewChatSession, ChatMessage,
    TokenUsage, UserSlackIntegration, Flow, FlowCrew, FlowExecution, CrewOutput
)
from .forms import AgentForm, TaskForm, CrewForm

class CrewTaskInline(admin.TabularInline):
    model = CrewTask
    extra = 1

@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ('name', 'process', 'verbose')
    filter_horizontal = ('agents',)
    inlines = [CrewTaskInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'agents', 'process', 'verbose', 'manager_llm', 'function_calling_llm', 'config', 'max_rpm', 'language', 'language_file', 'memory', 'cache', 'embedder', 'full_output', 'share_crew', 'output_log_file', 'manager_agent', 'manager_callbacks', 'prompt_file', 'planning', 'planning_llm')
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['agents'].widget.can_add_related = True
        form.base_fields['agents'].widget.can_change_related = True
        return form

@admin.register(CrewExecution)
class CrewExecutionAdmin(admin.ModelAdmin):
    list_display = ('crew', 'user', 'client', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('crew__name', 'user__username', 'client__name')
    readonly_fields = ('created_at', 'updated_at', 'human_input_request', 'human_input_response', 'error_message')
    fieldsets = (
        (None, {
            'fields': ('crew', 'user', 'client', 'status', 'inputs', 'crew_output')
        }),
        ('Human Input', {
            'fields': ('human_input_request', 'human_input_response')
        }),
        ('Error Information', {
            'fields': ('error_message',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

@admin.register(CrewMessage)
class CrewMessageAdmin(admin.ModelAdmin):
    list_display = ('execution', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('execution__crew__name', 'content')

@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    form = AgentForm
    list_display = ('name', 'role', 'llm', 'function_calling_llm', 'verbose', 'allow_delegation', 'allow_code_execution')
    list_filter = ('verbose', 'allow_delegation', 'allow_code_execution', 'use_system_prompt', 'respect_context_window')
    search_fields = ('name', 'role', 'goal', 'backstory')
    filter_horizontal = ('tools',)
    fieldsets = (
        (None, {
            'fields': ('name', 'role', 'goal', 'backstory', 'llm', 'tools')
        }),
        ('Advanced options', {
            'classes': ('collapse',),
            'fields': ('function_calling_llm', 'max_iter', 'max_rpm', 'max_execution_time', 'verbose', 'allow_delegation', 'step_callback', 'cache', 'system_template', 'prompt_template', 'response_template', 'allow_code_execution', 'max_retry_limit', 'use_system_prompt', 'respect_context_window'),
        }),
    )

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    form = TaskForm
    list_display = ('description', 'agent', 'async_execution', 'human_input', 'output_type')
    list_filter = ('async_execution', 'human_input')
    filter_horizontal = ('tools', 'context')
    search_fields = ('description', 'agent__name', 'expected_output')
    readonly_fields = ('output',)

    def output_type(self, obj):
        if obj.output_json:
            return 'JSON'
        elif obj.output_pydantic:
            return 'Pydantic'
        elif obj.output_file:
            return 'File'
        else:
            return 'Default'
    output_type.short_description = 'Output Type'

    fieldsets = (
        (None, {
            'fields': ('description', 'agent', 'expected_output', 'tools', 'async_execution', 'context')
        }),
        ('Advanced options', {
            'classes': ('collapse',),
            'fields': ('config', 'output_json', 'output_pydantic', 'output_file', 'human_input', 'converter_cls'),
        }),
        ('Output', {
            'fields': ('output',),
        }),
    )

@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description', 'function')

@admin.register(SlackChannelClientMapping)
class SlackChannelClientMappingAdmin(admin.ModelAdmin):
    list_display = ('channel_id', 'team_id', 'client', 'created_at')
    search_fields = ('channel_id', 'team_id')
    list_filter = ('team_id', 'created_at')

@admin.register(ToolRun)
class ToolRunAdmin(admin.ModelAdmin):
    list_display = ('tool', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'is_deleted')
    search_fields = ('tool__name', 'error')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(AgentToolSettings)
class AgentToolSettingsAdmin(admin.ModelAdmin):
    list_display = ('agent', 'tool', 'force_output_as_result')
    list_filter = ('force_output_as_result',)
    search_fields = ('agent__name', 'tool__name')

@admin.register(ExecutionStage)
class ExecutionStageAdmin(admin.ModelAdmin):
    list_display = ('execution', 'stage_type', 'title', 'status', 'created_at')
    list_filter = ('stage_type', 'status', 'created_at')
    search_fields = ('title', 'content', 'execution__crew__name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user', 'agent', 'client', 'participant_type', 'created_at', 'updated_at')
    list_filter = ('participant_type', 'is_active', 'created_at')
    search_fields = ('session_id', 'user__username', 'agent__name', 'title')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CrewChatSession)
class CrewChatSessionAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'crew_execution', 'status', 'last_activity')
    list_filter = ('status', 'last_activity')
    search_fields = ('conversation__title', 'crew_execution__crew__name')
    readonly_fields = ('last_activity',)

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'is_agent', 'timestamp', 'is_deleted')
    list_filter = ('is_agent', 'is_deleted', 'timestamp')
    search_fields = ('content', 'conversation__session_id', 'user__username')
    readonly_fields = ('timestamp',)

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'model', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'timestamp')
    list_filter = ('model', 'timestamp')
    search_fields = ('conversation__session_id', 'model')
    readonly_fields = ('timestamp',)

@admin.register(UserSlackIntegration)
class UserSlackIntegrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'team_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__username', 'team_name', 'team_id')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

class FlowCrewInline(admin.TabularInline):
    model = FlowCrew
    extra = 1

@admin.register(FlowCrew)
class FlowCrewAdmin(admin.ModelAdmin):
    list_display = ('flow', 'crew', 'order')
    list_filter = ('flow', 'crew')
    search_fields = ('flow__name', 'crew__name')

@admin.register(FlowExecution)
class FlowExecutionAdmin(admin.ModelAdmin):
    list_display = ('flow', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('flow__name',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CrewOutput)
class CrewOutputAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
    search_fields = ('raw',)
