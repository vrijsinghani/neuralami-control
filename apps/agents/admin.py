from django.contrib import admin
from .models import Crew, CrewExecution, CrewMessage, Agent, Task, Tool, CrewTask, SlackChannelClientMapping
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

