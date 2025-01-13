from rest_framework import serializers
from apps.agents.models import Agent, Task, Tool, Crew, CrewTask

# Tool Serializers
class GoogleAnalyticsToolSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=True)
    start_date = serializers.CharField(default="28daysAgo")
    end_date = serializers.CharField(default="today") 
    metrics = serializers.CharField(default="totalUsers,sessions")
    dimensions = serializers.CharField(default="date")
    dimension_filter = serializers.CharField(required=False, allow_null=True)
    metric_filter = serializers.CharField(default="sessions>10")
    currency_code = serializers.CharField(required=False, allow_null=True)
    keep_empty_rows = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(default=1000)
    offset = serializers.IntegerField(required=False, allow_null=True)
    data_format = serializers.ChoiceField(
        choices=['raw', 'summary', 'compact'],
        default='raw'
    )
    top_n = serializers.IntegerField(required=False, allow_null=True)
    time_granularity = serializers.ChoiceField(
        choices=['daily', 'weekly', 'monthly', 'auto'],
        default='auto'
    )
    aggregate_by = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True
    )
    metric_aggregation = serializers.ChoiceField(
        choices=['sum', 'average', 'min', 'max'],
        default='sum'
    )
    include_percentages = serializers.BooleanField(default=False)
    normalize_metrics = serializers.BooleanField(default=False)
    round_digits = serializers.IntegerField(required=False, allow_null=True)
    include_period_comparison = serializers.BooleanField(default=False)
    detect_anomalies = serializers.BooleanField(default=False)
    moving_average_window = serializers.IntegerField(required=False, allow_null=True)

class ImageConversionSerializer(serializers.Serializer):
    image = serializers.ImageField(required=True)
    quality = serializers.IntegerField(
        min_value=1, 
        max_value=100, 
        default=65,  
        required=False
    )
    max_width = serializers.IntegerField(
        min_value=1,
        default=1920,  # Standard HD width
        required=False,
        allow_null=True
    )
    max_height = serializers.IntegerField(
        min_value=1,
        default=1080,  # Standard HD height
        required=False,
        allow_null=True
    )
from rest_framework import serializers
from apps.agents.models import Agent, Task, Tool, Crew, CrewTask

class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = ['id', 'tool_class', 'tool_subclass', 'name', 'description', 'module_path']

class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = [
            'id', 'name', 'role', 'goal', 'backstory', 'llm', 'tools',
            'function_calling_llm', 'max_iter', 'max_rpm', 'max_execution_time',
            'verbose', 'allow_delegation', 'step_callback', 'cache',
            'system_template', 'prompt_template', 'response_template',
            'allow_code_execution', 'max_retry_limit', 'use_system_prompt',
            'respect_context_window', 'avatar'
        ]

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id', 'description', 'agent', 'expected_output', 'tools',
            'async_execution', 'context', 'config', 'output_json',
            'output_pydantic', 'output_file', 'output', 'callback',
            'human_input', 'converter_cls', 'crew_execution'
        ]

class CrewTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrewTask
        fields = ['crew', 'task', 'order']

class CrewSerializer(serializers.ModelSerializer):
    tasks = CrewTaskSerializer(source='crew_tasks', many=True, read_only=True)

    class Meta:
        model = Crew
        fields = [
            'id', 'name', 'agents', 'tasks', 'process', 'verbose',
            'manager_llm', 'function_calling_llm', 'config', 'max_rpm',
            'language', 'language_file', 'memory', 'cache', 'embedder',
            'full_output', 'share_crew', 'output_log_file', 'manager_agent',
            'manager_callbacks', 'prompt_file', 'planning', 'planning_llm',
            'input_variables'
        ]