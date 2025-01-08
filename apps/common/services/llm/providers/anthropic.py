"""Anthropic API provider implementation."""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import anthropic
import httpx

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class AnthropicProvider(BaseLLMProvider):
    """Direct Anthropic API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize Anthropic provider with configuration."""
        super().__init__(config)
        
        # Get provider settings
        self.api_base = config.api_base_url
        self.api_version = config.api_version
        self.max_retries = config.max_retries
        
        # Initialize client with proper settings
        self.client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=self.api_base,
            max_retries=self.max_retries,
            timeout=config.timeout
        )
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 1000)
        
        # Set default model if not specified
        self.model_name = config.default_model or 'claude-3-sonnet-20240229'
        
        # Cache settings
        self._cache_config = config.get_cache_config()
        self._rate_limits = config.get_rate_limits()
        self._streaming_config = config.get_streaming_config()
        
        # Initialize models cache
        self.available_models = {}
    
    async def initialize(self):
        """Initialize provider and fetch available models."""
        try:
            if self._cache_config['enable_model_cache']:
                # TODO: Check cache first
                pass
                
            self.available_models = await self._fetch_available_models()
            
            # Validate model name
            if self.model_name not in self.available_models:
                logger.warning(f"Model {self.model_name} not found, falling back to claude-3-sonnet-20240229")
                self.model_name = 'claude-3-sonnet-20240229'
            
            # Update max tokens based on model limits
            self.max_tokens = min(
                self.max_tokens,
                self.available_models[self.model_name]['max_output_tokens']
            )
            
            if self._cache_config['enable_model_cache']:
                # TODO: Cache the models
                pass
                
        except Exception as e:
            logger.error(f"Error initializing Anthropic provider: {str(e)}")
            raise
    
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion using Anthropic API."""
        try:
            # Get model parameters with overrides
            model_params = self.config.get_model_parameters(
                kwargs.get('model_name', self.model_name)
            )
            
            # Convert messages to Anthropic format
            anthropic_messages = []
            system_message = None
            
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                if role == 'system':
                    system_message = content
                    continue
                
                # Handle vision content
                if isinstance(content, list):
                    message_content = []
                    
                    for part in content:
                        if isinstance(part, dict) and 'mime_type' in part and 'data' in part:
                            # Clean and validate image data
                            data = part['data']
                            if ',' in data:  # Remove data URL prefix if present
                                data = data.split(',', 1)[1]
                            
                            # Add image content block
                            message_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": part['mime_type'],
                                    "data": data
                                }
                            })
                        else:
                            # Add text content block
                            text = str(part).strip()
                            if text:
                                message_content.append({
                                    "type": "text",
                                    "text": text
                                })
                else:
                    # Handle text-only content
                    message_content = [{
                        "type": "text",
                        "text": str(content)
                    }]
                
                anthropic_messages.append({
                    "role": "user" if role == "user" else "assistant",
                    "content": message_content
                })
            
            # Get streaming config if needed
            stream_config = self._streaming_config if stream else {}
            
            # Prepare request parameters
            request_params = {
                "model": kwargs.get('model_name', self.model_name),
                "messages": anthropic_messages,
                "temperature": kwargs.get('temperature', model_params.get('temperature', self.temperature)),
                "max_tokens": kwargs.get('max_tokens', model_params.get('max_tokens', self.max_tokens)),
                "stream": stream,
                "metadata": {
                    "user_id": str(self.config.user.id) if hasattr(self.config, 'user') else None
                }
            }
            
            # Only add system message if it exists
            if system_message:
                request_params["system"] = system_message
            
            # Get response
            response = await self.client.messages.create(**request_params)
            
            if stream:
                return response
            
            # Calculate costs
            model_info = self.available_models[self.model_name]
            input_cost = (response.usage.input_tokens / 1_000_000) * model_info['input_cost']
            output_cost = (response.usage.output_tokens / 1_000_000) * model_info['output_cost']
            
            return response.content[0].text, {
                'usage': {
                    'prompt_tokens': response.usage.input_tokens,
                    'completion_tokens': response.usage.output_tokens,
                    'total_tokens': response.usage.input_tokens + response.usage.output_tokens
                },
                'model': self.model_name,
                'cost': {
                    'input_cost': input_cost,
                    'output_cost': output_cost,
                    'total_cost': input_cost + output_cost
                }
            }
            
        except Exception as e:
            logger.error(f"Anthropic completion error: {str(e)}", exc_info=True)
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using Anthropic API."""
        raise NotImplementedError("Anthropic does not currently support embeddings")
    
    async def _load_image_from_url(self, url: str) -> str:
        """Load image data from URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Error loading image from URL: {str(e)}")
            raise 
    
    async def _fetch_available_models(self) -> Dict[str, dict]:
        """Fetch available models from Anthropic API."""
        try:
            response = await self.client.models.list()
            
            models = {}
            for model in response.data:
                model_id = model.id
                
                # Determine model capabilities and pricing tiers
                is_opus = 'opus' in model_id.lower()
                is_sonnet = 'sonnet' in model_id.lower()
                is_haiku = 'haiku' in model_id.lower()
                
                # Set pricing based on model tier (in USD per million tokens)
                if is_opus:
                    input_cost = 15.0
                    output_cost = 75.0
                    max_tokens = 4096
                elif is_sonnet:
                    input_cost = 3.0
                    output_cost = 15.0
                    max_tokens = 4096
                else:  # Haiku
                    input_cost = 0.25
                    output_cost = 1.25
                    max_tokens = 4096
                
                # Build model info
                models[model_id] = {
                    'description': f"Anthropic {model_id} model",
                    'input_tokens': 200000 if is_opus else (32768 if is_sonnet else 16384),
                    'max_output_tokens': max_tokens,
                    'input_cost': input_cost,
                    'output_cost': output_cost,
                    'supports_vision': hasattr(model, 'capabilities') and getattr(model.capabilities, 'vision', False),
                    'supports_json': True,
                    'supports_functions': False,
                    'status': 'stable',
                    'default_parameters': {
                        'temperature': 0.7,
                        'top_p': 0.95,
                        'top_k': None,
                        'frequency_penalty': 0,
                        'presence_penalty': 0
                    },
                    'system_info': {
                        'id': model_id,
                        'display_name': getattr(model, 'name', model_id)
                    }
                }
            
            # If no models found, return default set
            if not models:
                return {
                    'claude-3-sonnet-20240229': {
                        'description': 'Claude 3 Sonnet',
                        'input_tokens': 32768,
                        'max_output_tokens': 4096,
                        'input_cost': 3.0,
                        'output_cost': 15.0,
                        'supports_vision': True,
                        'supports_json': True,
                        'supports_functions': False,
                        'status': 'stable',
                        'default_parameters': {
                            'temperature': 0.7,
                            'top_p': 0.95,
                            'frequency_penalty': 0,
                            'presence_penalty': 0
                        }
                    }
                }
            
            return models
            
        except Exception as e:
            logger.error(f"Error fetching Anthropic models: {str(e)}")
            # Return a minimal set of known models as fallback
            return {
                'claude-3-sonnet-20240229': {
                    'description': 'Claude 3 Sonnet',
                    'input_tokens': 32768,
                    'max_output_tokens': 4096,
                    'input_cost': 3.0,
                    'output_cost': 15.0,
                    'supports_vision': True,
                    'supports_json': True,
                    'supports_functions': False,
                    'status': 'stable',
                    'default_parameters': {
                        'temperature': 0.7,
                        'top_p': 0.95,
                        'frequency_penalty': 0,
                        'presence_penalty': 0
                    }
                }
            } 