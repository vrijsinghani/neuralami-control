"""
Models for common functionality including LLM configuration and tracking.
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.conf import settings
import json
from typing import Any, Optional

User = get_user_model()

class ProviderType(models.TextChoices):
	"""Available LLM providers."""
	LITELLM = 'litellm', 'LiteLLM'
	OPENAI = 'openai', 'OpenAI'
	ANTHROPIC = 'anthropic', 'Anthropic'
	GEMINI = 'gemini', 'Google Gemini'
	OPENROUTER = 'openrouter', 'OpenRouter'
	OLLAMA = 'ollama', 'Ollama'

class ModelFamily(models.TextChoices):
	"""Model families for cost tracking and capabilities."""
	GPT4 = 'gpt4', 'GPT-4'
	GPT35 = 'gpt35', 'GPT-3.5'
	CLAUDE3 = 'claude3', 'Claude 3'
	CLAUDE2 = 'claude2', 'Claude 2'
	GEMINI = 'gemini', 'Gemini'
	LLAMA = 'llama', 'Llama'
	MISTRAL = 'mistral', 'Mistral'
	CUSTOM = 'custom', 'Custom'

class LLMConfiguration(models.Model):
	"""Configuration for LLM providers and settings."""
	
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	
	# Provider Settings
	provider_type = models.CharField(
		max_length=20,
		choices=ProviderType.choices,
		default=ProviderType.GEMINI
	)
	fallback_provider = models.ForeignKey(
		'self',
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name='fallback_configs'
	)
	
	# Model Settings
	default_model = models.CharField(max_length=100)
	model_parameters = models.JSONField(
		default=dict,
		blank=True,
		help_text="Default parameters for model (temperature, top_p, etc.)",
		null=True
	)
	
	# Rate Limiting
	requests_per_minute = models.IntegerField(default=60)
	tokens_per_minute = models.IntegerField(default=40000)
	
	# Caching Settings
	enable_response_cache = models.BooleanField(
		default=True,
		help_text="Enable caching of LLM responses"
	)
	response_cache_ttl = models.IntegerField(
		default=3600,
		help_text="Time to live for cached responses in seconds"
	)
	enable_model_cache = models.BooleanField(
		default=True,
		help_text="Enable caching of available models"
	)
	model_cache_ttl = models.IntegerField(
		default=3600,
		help_text="Time to live for cached model information in seconds"
	)
	
	# Provider-Specific Settings
	provider_settings = models.JSONField(
		default=dict,
		blank=True,
		null=True,
		help_text="Provider-specific settings and overrides"
	)
	
	# API Authentication
	api_key = models.CharField(
		max_length=255,
		blank=True,
		help_text="Primary API key for the provider"
	)
	api_key_secondary = models.CharField(
		max_length=255,
		blank=True,
		help_text="Secondary/backup API key"
	)
	organization_id = models.CharField(
		max_length=255,
		blank=True,
		help_text="Organization ID for providers that require it"
	)
	
	# Streaming Settings
	streaming_config = models.JSONField(
		default=dict,
		blank=True,
		null=True,
		help_text="Configuration for streaming responses"
	)
	
	class Meta:
		verbose_name = "LLM Configuration"
		verbose_name_plural = "LLM Configurations"
		ordering = ['-created_at']
	
	def __str__(self):
		return self.name
	
	def get_provider_setting(self, key: str, default: Any = None) -> Any:
		"""Get a provider-specific setting with fallback to default."""
		default_settings = {
			'rate_limits': {},
			'credentials': {},
			'model_parameters': {},
			'api_base': None,
			'api_version': None,
			'timeout': 30,
			'max_retries': 3
		}
		settings = self.provider_settings or {}
		settings = {**default_settings, **settings}
		return settings.get(self.provider_type, {}).get(key, default)
	
	def get_model_parameters(self, model_name: str = None) -> dict:
		"""Get model parameters with optional model-specific overrides."""
		default_params = {
			"temperature": 0.7,
			"top_p": 1.0,
			"max_tokens": 8192,
			"presence_penalty": 0,
			"frequency_penalty": 0
		}
		params = self.model_parameters or {}
		params = {**default_params, **params}  # Merge with defaults
		if model_name:
			model_specific = self.provider_settings.get(self.provider_type, {}).get('model_parameters', {})
			params.update(model_specific.get(model_name, {}))
		return params
	
	def get_streaming_config(self) -> dict:
		"""Get streaming configuration with defaults."""
		defaults = {
			'stream_chunk_size': 100,
			'stream_timeout': 30,
			'max_tokens_per_chunk': 50,
			'chunk_separator': '\n',
			'retry_on_timeout': True,
			'buffer_size': 4096
		}
		config = self.streaming_config or {}
		return {**defaults, **config}
	
	def get_rate_limits(self) -> dict:
		"""Get rate limiting configuration with provider-specific overrides."""
		limits = {
			'requests_per_minute': self.requests_per_minute,
			'tokens_per_minute': self.tokens_per_minute
		}
		provider_limits = self.get_provider_setting('rate_limits', {})
		return {**limits, **provider_limits}
	
	def get_cache_config(self) -> dict:
		"""Get caching configuration."""
		return {
			'enable_response_cache': self.enable_response_cache,
			'response_cache_ttl': self.response_cache_ttl,
			'enable_model_cache': self.enable_model_cache,
			'model_cache_ttl': self.model_cache_ttl
		}
	
	def get_api_credentials(self) -> dict:
		"""Get API credentials with provider-specific overrides."""
		creds = {
			'api_key': self.api_key,
			'api_key_secondary': self.api_key_secondary,
			'organization_id': self.organization_id
		}
		provider_creds = self.get_provider_setting('credentials', {})
		return {**creds, **provider_creds}
	
	@property
	def timeout(self) -> int:
		"""Get provider timeout from settings."""
		return self.provider_settings.get('timeout', 30)
		
	@property
	def api_base_url(self) -> Optional[str]:
		"""Get provider API base URL from settings."""
		return self.provider_settings.get('api_base')
		
	@property
	def api_version(self) -> Optional[str]:
		"""Get provider API version from settings."""
		return self.provider_settings.get('api_version')
		
	@property
	def max_retries(self) -> int:
		"""Get provider max retries from settings."""
		return self.provider_settings.get('max_retries', 3)

class TokenUsage(models.Model):
	"""Track token usage for LLM interactions."""
	
	user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
	model = models.CharField(max_length=100)
	prompt_tokens = models.IntegerField()
	completion_tokens = models.IntegerField()
	total_cost = models.DecimalField(max_digits=10, decimal_places=6, null=True)
	timestamp = models.DateTimeField(default=timezone.now)
	
	# Optional metadata
	request_type = models.CharField(max_length=50, blank=True)  # e.g., 'chat', 'completion', etc.
	session_id = models.CharField(max_length=100, blank=True)
	provider_type = models.CharField(
		max_length=20,
		choices=ProviderType.choices,
		null=True,
		blank=True
	)
	
	class Meta:
		indexes = [
			models.Index(fields=['user', 'timestamp']),
			models.Index(fields=['model', 'timestamp']),
			models.Index(fields=['provider_type', 'timestamp']),
		]
	
	def __str__(self):
		return f"{self.model} - {self.prompt_tokens + self.completion_tokens} tokens"

class LLMTestHarnessModel(models.Model):
	"""Model for LLM test harness. This is a proxy model for admin interface."""
	
	class Meta:
		managed = False  # No database table needed
		verbose_name = 'LLM Test Harness'
		verbose_name_plural = 'LLM Test Harness'
		app_label = 'common'
 
	