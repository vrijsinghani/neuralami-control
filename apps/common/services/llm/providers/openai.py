"""OpenAI API provider implementation."""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
from openai import AsyncOpenAI
import httpx

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(BaseLLMProvider):
    """Direct OpenAI API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize OpenAI provider with configuration."""
        super().__init__(config)
        
        # Get provider settings
        self.api_base = config.api_base_url
        self.api_version = config.api_version
        self.max_retries = config.max_retries
        
        # Initialize client with proper settings
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=self.api_base or "https://api.openai.com/v1",
            max_retries=self.max_retries,
            timeout=httpx.Timeout(config.timeout)
        )
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 200000)
        
        # Set default model if not specified
        self.model_name = config.default_model or 'gpt-3.5-turbo'
        
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
                logger.warning(f"Model {self.model_name} not found, falling back to gpt-3.5-turbo")
                self.model_name = 'gpt-3.5-turbo'
            
            # Update max tokens based on model limits
            self.max_tokens = min(
                self.max_tokens,
                self.available_models[self.model_name]['output_tokens']
            )
            
            if self._cache_config['enable_model_cache']:
                # TODO: Cache the models
                pass
                
        except Exception as e:
            logger.error(f"Error initializing OpenAI provider: {str(e)}")
            raise
    
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion using OpenAI API."""
        try:
            # Get model parameters with overrides
            model_params = self.config.get_model_parameters(
                kwargs.get('model_name', self.model_name)
            )
            
            # Convert messages to OpenAI format
            openai_messages = []
            
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                # Handle vision content
                if isinstance(content, list):
                    message_content = []
                    
                    # Add text first if present
                    text_parts = [part for part in content if not isinstance(part, dict) or 'mime_type' not in part]
                    if text_parts:
                        message_content.append({
                            "type": "text",
                            "text": " ".join(str(part) for part in text_parts)
                        })
                    
                    # Add images
                    for part in content:
                        if isinstance(part, dict) and 'mime_type' in part and 'data' in part:
                            # Clean and validate image data
                            data = part['data']
                            if ',' in data:  # Remove data URL prefix if present
                                data = data.split(',', 1)[1]
                            
                            # Add image content block
                            message_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{data}",
                                    "detail": kwargs.get('image_detail', 'auto')
                                }
                            })
                    
                    openai_messages.append({
                        "role": role,
                        "content": message_content
                    })
                else:
                    # Handle text-only content
                    openai_messages.append({
                        "role": role,
                        "content": [{
                            "type": "text",
                            "text": str(content)
                        }]
                    })
            
            # Prepare request parameters
            request_params = {
                "model": kwargs.get('model_name', self.model_name),
                "messages": openai_messages,
                "temperature": kwargs.get('temperature', model_params.get('temperature', self.temperature)),
                "max_tokens": kwargs.get('max_tokens', model_params.get('max_tokens', self.max_tokens)),
                "stream": stream
            }
            
            # Add optional parameters if specified
            for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
                if param in kwargs:
                    request_params[param] = kwargs[param]
            
            # Handle response_format parameter separately
            if 'response_format' in kwargs:
                response_format = kwargs['response_format']
                if isinstance(response_format, dict) and 'schema' in response_format:
                    # Remove schema property if present
                    response_format = {k: v for k, v in response_format.items() if k != 'schema'}
                request_params['response_format'] = response_format
            
            # Make request
            response = await self.client.chat.completions.create(**request_params)
            
            if stream:
                return self._process_stream(response)
            
            # Extract response and metadata
            completion = response.choices[0].message.content
            
            return completion, {
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                },
                'model': response.model,
                'finish_reason': response.choices[0].finish_reason
            }
            
        except Exception as e:
            logger.error(f"OpenAI completion error: {str(e)}", exc_info=True)
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using OpenAI API."""
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embeddings error: {str(e)}")
            raise 
    
    async def _fetch_available_models(self) -> Dict[str, dict]:
        """Fetch available models from OpenAI API."""
        try:
            response = await self.client.models.list()
            
            models = {}
            for model in response.data:
                model_id = model.id
                
                # Skip non-chat and non-embedding models
                if not (model_id.startswith('gpt-') or model_id.startswith('text-embedding-')):
                    continue
                
                # Determine model capabilities and pricing tiers
                is_gpt4 = 'gpt-4' in model_id
                is_gpt4_turbo = 'gpt-4-turbo' in model_id
                is_gpt4_vision = 'vision' in model_id
                is_gpt35 = 'gpt-3.5' in model_id
                is_embedding = 'embedding' in model_id
                is_preview = 'preview' in model_id
                
                if is_embedding:
                    # Embedding models
                    is_large = 'large' in model_id
                    models[model_id] = {
                        'description': f"OpenAI embedding model: {model_id}",
                        'input_tokens': 8191,
                        'output_dimension': 3072 if is_large else 1536,
                        'input_cost': 0.13 if is_large else 0.02,
                        'supports_batch': True,
                        'status': 'stable',
                        'system_info': {
                            'id': model.id,
                            'created': model.created,
                            'owned_by': model.owned_by
                        }
                    }
                else:
                    # Chat models
                    if is_gpt4_turbo:
                        input_cost = 10.0
                        output_cost = 30.0
                        context_window = 128000
                    elif is_gpt4:
                        input_cost = 30.0
                        output_cost = 60.0
                        context_window = 32768 if is_preview else 8192
                    else:  # GPT-3.5
                        input_cost = 0.5
                        output_cost = 1.5
                        context_window = 16385
                    
                    models[model_id] = {
                        'description': f"OpenAI {'GPT-4' if is_gpt4 else 'GPT-3.5'} model",
                        'input_tokens': context_window,
                        'output_tokens': 4096,
                        'input_cost': input_cost,
                        'output_cost': output_cost,
                        'supports_vision': is_gpt4_vision,
                        'supports_json': True,
                        'supports_functions': True,
                        'status': 'preview' if is_preview else 'stable',
                        'default_parameters': {
                            'temperature': 0.7,
                            'top_p': 0.95,
                            'frequency_penalty': 0,
                            'presence_penalty': 0
                        },
                        'system_info': {
                            'id': model.id,
                            'created': model.created,
                            'owned_by': model.owned_by
                        }
                    }
            
            # If no models found, return default set
            if not models:
                return {
                    'gpt-3.5-turbo': {
                        'description': 'OpenAI GPT-3.5 model',
                        'input_tokens': 16385,
                        'output_tokens': 4096,
                        'input_cost': 0.5,
                        'output_cost': 1.5,
                        'supports_vision': False,
                        'supports_json': True,
                        'supports_functions': True,
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
            logger.error(f"Error fetching OpenAI models: {str(e)}")
            # Return a minimal set of known models as fallback
            return {
                'gpt-3.5-turbo': {
                    'description': 'OpenAI GPT-3.5 model',
                    'input_tokens': 16385,
                    'output_tokens': 4096,
                    'input_cost': 0.5,
                    'output_cost': 1.5,
                    'supports_vision': False,
                    'supports_json': True,
                    'supports_functions': True,
                    'status': 'stable',
                    'default_parameters': {
                        'temperature': 0.7,
                        'top_p': 0.95,
                        'frequency_penalty': 0,
                        'presence_penalty': 0
                    }
                }
            } 