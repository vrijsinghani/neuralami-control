"""Ollama API provider implementation."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import httpx

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class OllamaProvider(BaseLLMProvider):
    """Direct Ollama API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize Ollama provider with configuration."""
        super().__init__(config)
        
        
        # Get API base from provider settings
        self.api_base = config.api_base_url
        
        if not self.api_base:
            raise ValueError("No api_base specified in provider settings for Ollama")
            
        self.api_version = config.api_version
        self.max_retries = config.max_retries
        
        
        # Initialize client with proper settings
        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=config.timeout
        )
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 8192)
        
        # Set default model from config
        self.model_name = config.default_model
        if not self.model_name:
            raise ValueError("No default model specified in configuration")
        
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
                logger.error(f"Model {self.model_name} not found in available models")
                raise ValueError(f"Model {self.model_name} not found in available models")
            
            # Get model info and set parameters
            model_info = self.available_models[self.model_name]
            self.default_parameters = {
                **model_info['default_parameters'],
                'temperature': self.temperature
            }
            
            if self._cache_config['enable_model_cache']:
                # TODO: Cache the models
                pass
                
        except Exception as e:
            logger.error(f"Error initializing Ollama provider: {str(e)}")
            raise
    
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion using Ollama API."""
        try:
            # Get model parameters with overrides
            model_name = kwargs.get('model_name', self.model_name)
            model_params = self.config.get_model_parameters(model_name)
            
            # Verify model supports vision if images are present
            model_info = self.available_models.get(model_name)
            if not model_info:
                raise ValueError(f"Model {model_name} not found in available models")
            
            # Get streaming config if needed
            stream_config = self._streaming_config if stream else {}
            
            # Convert messages to Ollama format
            prompt = ""
            system_message = None
            image_data = None  # Only store one image as per Ollama API
            has_vision_content = False
            
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                if role == 'system':
                    system_message = content
                    continue
                
                # Handle vision content
                if isinstance(content, list):
                    has_vision_content = True
                    current_text = []
                    
                    for part in content:
                        if isinstance(part, dict) and 'mime_type' in part and 'data' in part:
                            # Clean and validate image data
                            data = part['data']
                            if ',' in data:  # Remove data URL prefix if present
                                data = data.split(',', 1)[1]
                            
                            # Validate MIME type
                            mime_type = part['mime_type'].lower()
                            if not mime_type.startswith('image/'):
                                raise ValueError(f"Invalid MIME type for image: {mime_type}")
                            
                            # Store image data (only keep the last one as Ollama only supports one image)
                            image_data = data
                        else:
                            # Collect text parts
                            text = str(part).strip()
                            if text:
                                current_text.append(text)
                    
                    # Add collected text to prompt
                    if current_text:
                        text_content = ' '.join(current_text)
                        if role == 'assistant':
                            prompt += f"Assistant: {text_content}\n"
                        else:
                            prompt += f"Human: {text_content}\n"
                else:
                    # Handle text-only content
                    if role == 'assistant':
                        prompt += f"Assistant: {content}\n"
                    else:
                        prompt += f"Human: {content}\n"
            
            # Verify vision support if needed
            if has_vision_content and not model_info.get('supports_vision'):
                raise ValueError(f"Model {model_name} does not support vision tasks")
            
            prompt += "Assistant:"
            
            # Prepare request data
            request_data = {
                "model": model_name,
                "prompt": prompt.strip(),
                "stream": stream,
                "options": {
                    "temperature": kwargs.get('temperature', model_params.get('temperature', self.temperature)),
                    "num_predict": kwargs.get('max_tokens', model_params.get('max_tokens', self.max_tokens)),
                    "top_p": kwargs.get('top_p', model_params.get('top_p', 0.9)),
                    "repeat_penalty": kwargs.get('repeat_penalty', model_params.get('repeat_penalty', 1.1))
                }
            }
            
            # Add system message if present
            if system_message:
                request_data["system"] = system_message
            
            # Add image if present (as a string, not an array)
            if image_data:
                request_data["images"] = [image_data]  # Ollama expects an array of base64 strings
            
            # Log request data for debugging (excluding image data)
            debug_data = request_data.copy()
            if 'images' in debug_data:
                debug_data['images'] = [f"<{len(img)} bytes>" for img in debug_data['images']]
            
            # Make request
            try:
                response = await self.client.post(
                    "/api/generate",
                    json=request_data
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                error_text = e.response.text
                logger.error(f"Ollama API error: {error_text}")
                raise ValueError(f"Ollama API error: {error_text}")
            
            if stream:
                return self._process_stream(response)
            
            data = response.json()
            
            # Extract response and metadata
            response_text = data['response']
            total_duration = data.get('total_duration', 0)
            load_duration = data.get('load_duration', 0)
            prompt_eval_count = data.get('prompt_eval_count', 0)
            eval_count = data.get('eval_count', 0)
            
            # Estimate token counts (Ollama doesn't provide these)
            prompt_tokens = len(prompt.split())
            completion_tokens = len(response_text.split())
            
            return response_text, {
                'usage': {
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': prompt_tokens + completion_tokens
                },
                'model': model_name,
                'timings': {
                    'total_duration': total_duration,
                    'load_duration': load_duration,
                    'prompt_eval_count': prompt_eval_count,
                    'eval_count': eval_count
                }
            }
            
        except Exception as e:
            logger.error(f"Ollama completion error: {str(e)}", exc_info=True)
            raise
    
    async def _process_stream(self, response) -> AsyncGenerator[str, None]:
        """Process streaming response from Ollama."""
        try:
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if 'response' in data:
                            yield data['response']
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error processing Ollama stream: {str(e)}")
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using Ollama API."""
        try:
            response = await self.client.post("/api/embeddings", json={
                "model": self.model_name,
                "prompt": text
            })
            response.raise_for_status()
            data = response.json()
            return data['embedding']
        except Exception as e:
            logger.error(f"Ollama embeddings error: {str(e)}")
            raise 
    
    async def _fetch_available_models(self) -> Dict[str, dict]:
        """Fetch available models from Ollama API."""
        try:
            # First try to connect to Ollama server
            try:
                response = await self.client.get("/api/tags")
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Could not connect to Ollama server at {self.client.base_url}: {str(e)}")
                raise ConnectionError(f"Could not connect to Ollama server at {self.client.base_url}. Please ensure Ollama is running and accessible.")
            
            data = response.json()
            
            models = {}
            for model in data.get('models', []):
                model_name = model['name']
                
                try:
                    # Get model details
                    details_response = await self.client.post("/api/show", json={"name": model_name})
                    details_response.raise_for_status()
                    details = details_response.json()
                    
                    # Extract parameters from modelfile
                    parameters = {}
                    modelfile = details.get('modelfile', '')
                    for line in modelfile.split('\n'):
                        if line.startswith('PARAMETER'):
                            try:
                                _, key, value = line.split()
                                parameters[key] = float(value) if '.' in value else int(value)
                            except (ValueError, IndexError):
                                continue
                    
                    # Detect vision capabilities
                    modelfile_lower = modelfile.lower()
                    supports_vision = any(x in modelfile_lower for x in [
                        'clip',  # CLIP vision models
                        'llava',  # LLaVA models
                        'vision',  # Generic vision indicator
                        'image',   # Image processing
                        'multimodal'  # Multimodal models
                    ])
                    
                    # Detect code/JSON capabilities
                    supports_json = any(x in model_name.lower() for x in [
                        'starcoder',
                        'codellama',
                        'wizard-coder',
                        'deepseek-coder'
                    ])
                    
                    # Build model info
                    models[model_name] = {
                        'description': details.get('description', f"Ollama model: {model_name}"),
                        'context_window': parameters.get('num_ctx', 4096),
                        'max_output_tokens': parameters.get('num_ctx', 4096),
                        'supports_vision': supports_vision,
                        'supports_json': supports_json,
                        'supports_functions': False,
                        'status': 'stable',
                        'default_parameters': {
                            'num_ctx': parameters.get('num_ctx', 4096),
                            'temperature': parameters.get('temperature', 0.7),
                            'top_p': parameters.get('top_p', 0.9),
                            'repeat_penalty': parameters.get('repeat_penalty', 1.1)
                        },
                        'system_info': {
                            'size': model.get('size', 0),
                            'digest': model.get('digest', ''),
                            'modified_at': model.get('modified_at', ''),
                            'details': details
                        }
                    }
                except Exception as e:
                    logger.warning(f"Error getting details for model {model_name}: {str(e)}")
                    continue
            
            # If no models found, raise error
            if not models:
                raise ValueError("No models found in Ollama server. Please ensure models are installed.")
            
            return models
            
        except Exception as e:
            if isinstance(e, (ConnectionError, ValueError)):
                raise
            
            logger.error(f"Error fetching Ollama models: {str(e)}")
            raise ValueError(f"Failed to fetch models from Ollama server: {str(e)}") 