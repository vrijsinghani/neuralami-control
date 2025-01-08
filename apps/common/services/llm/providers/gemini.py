"""Google Gemini API provider implementation."""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import google.generativeai as genai
import httpx
import tiktoken

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    """Direct Google Gemini API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize Gemini provider with configuration."""
        super().__init__(config)
        
        # Initialize client
        genai.configure(api_key=config.api_key)
        self.model = None
        
        # Initialize tokenizer
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 1000000)
        
        # Set default model if not specified
        if not self.model_name:
            self.model_name = 'gemini-pro'  # Default to Gemini Pro
    
    async def initialize(self):
        """Initialize provider and fetch available models."""
        try:
            self.AVAILABLE_MODELS = await self._fetch_available_models()
            
            # Validate model name
            if self.model_name not in self.AVAILABLE_MODELS:
                logger.warning(f"Model {self.model_name} not found, falling back to gemini-pro")
                self.model_name = 'gemini-pro'
            
            # Update max tokens based on model limits
            model_info = self.AVAILABLE_MODELS[self.model_name]
            self.max_tokens = min(
                self.max_tokens,
                model_info.get('output_tokens', 2048)
            )
            
            # Initialize the model
            self.model = genai.GenerativeModel(self.model_name)
            
        except Exception as e:
            logger.error(f"Error initializing Gemini provider: {str(e)}")
            raise
    
    async def _fetch_available_models(self) -> dict:
        """Fetch available models from Gemini API."""
        try:
            # List all available models
            models = {}
            available_models = genai.list_models()
            
            if not available_models:
                logger.error("No models returned from Gemini API")
                raise Exception("No models returned from Gemini API")
            
            for model in available_models:
                # Only include Gemini models that support text generation
                if (model.name.startswith('models/gemini-') and 
                    not model.name.endswith('vision') and 
                    not model.name.endswith('embedding')):
                    
                    # Extract the model name without the 'models/' prefix
                    model_name = model.name.split('/')[-1]
                    # Extract the base model ID (e.g., gemini-1.5-pro from gemini-1.5-pro-latest)
                    base_model = model_name.split('-latest')[0] if '-latest' in model_name else model_name
                    
                    models[base_model] = {
                        "name": base_model,
                        "description": model.description,
                        "context_window": model.input_token_limit,
                        "input_tokens": model.input_token_limit,
                        "output_tokens": model.output_token_limit,
                        "supports_vision": False,
                        "supports_json": True,
                        "supports_functions": True,
                        "temperature": getattr(model, 'temperature', 0.7),
                        "max_temperature": getattr(model, 'max_temperature', 1.0),
                        "top_p": getattr(model, 'top_p', 1.0),
                        "top_k": getattr(model, 'top_k', 1)
                    }
                
                # Handle vision models separately
                elif model.name.startswith('models/gemini-') and model.name.endswith('vision'):
                    model_name = model.name.split('/')[-1]
                    base_model = model_name.split('-latest')[0] if '-latest' in model_name else model_name
                    
                    models[base_model] = {
                        "name": base_model,
                        "description": model.description,
                        "context_window": model.input_token_limit,
                        "input_tokens": model.input_token_limit,
                        "output_tokens": model.output_token_limit,
                        "supports_vision": True,
                        "supports_json": True,
                        "supports_functions": True,
                        "temperature": getattr(model, 'temperature', 0.7),
                        "max_temperature": getattr(model, 'max_temperature', 1.0),
                        "top_p": getattr(model, 'top_p', 1.0),
                        "top_k": getattr(model, 'top_k', 1)
                    }
                else:
                    pass
            
            if not models:
                logger.error("No Gemini models found after processing API response")
                raise Exception("No Gemini models found")
            
            # Log final models dictionary
            #logger.debug(f"Final available models: {models}")
            return models
            
        except Exception as e:
            logger.error(f"Error fetching Gemini models: {str(e)}", exc_info=True)
            raise
        
    async def get_completion(self, messages: List[dict], **kwargs) -> Tuple[str, dict]:
        """Get completion from Gemini."""
        try:
            # Initialize model if needed
            if not self.model:
                self.model = genai.GenerativeModel(self.model_name)
                
            # Convert messages to Gemini format
            gemini_messages = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                # Handle vision content
                if isinstance(content, list):
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and 'mime_type' in part:
                            parts.append({
                                'inline_data': {
                                    'mime_type': part['mime_type'],
                                    'data': part['data']
                                }
                            })
                        else:
                            parts.append({'text': str(part)})
                    
                    gemini_messages.append({
                        'role': 'user' if role == 'user' else 'model',
                        'parts': parts
                    })
                else:
                    # Handle text-only content
                    gemini_messages.append({
                        'role': 'user' if role == 'user' else 'model',
                        'parts': [{'text': str(content)}]
                    })
            
            # Get generation config
            generation_config = genai.types.GenerationConfig(
                temperature=kwargs.get('temperature', self.temperature),
                max_output_tokens=kwargs.get('max_tokens', self.max_tokens),
                top_p=kwargs.get('top_p', 1.0),
                top_k=kwargs.get('top_k', 1)
            )
            
            # Generate response
            response = self.model.generate_content(
                gemini_messages,
                generation_config=generation_config
            )
            
            if not response.text:
                raise Exception("Empty response from Gemini")
                
            # Count tokens using tiktoken
            prompt_text = str(gemini_messages)  # Convert messages to string for token counting
            prompt_tokens = len(self.tokenizer.encode(prompt_text))
            completion_tokens = len(self.tokenizer.encode(response.text))
            total_tokens = prompt_tokens + completion_tokens
            
            # Extract usage info
            metadata = {
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                },
                "model": self.model_name
            }
            
            return response.text, metadata
            
        except Exception as e:
            logger.error(f"Error in Gemini completion: {str(e)}", exc_info=True)
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using Gemini API."""
        try:
            embedding_model = genai.GenerativeModel('embedding-001')
            result = await embedding_model.embed_content(
                {"text": text},
                task_type="retrieval_query"
            )
            return result.embedding
        except Exception as e:
            logger.error(f"Gemini embeddings error: {str(e)}")
            raise
    
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
    
    def _convert_messages_to_prompt(self, messages: List[dict]) -> str:
        """Convert messages to Gemini prompt format."""
        prompt = []
        system_message = None
        
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            if role == 'system':
                system_message = content
                continue
                
            if role == 'assistant':
                prompt.append(f"Assistant: {content}")
            else:
                prompt.append(f"User: {content}")
                
        # Add system message at the start if present
        if system_message:
            prompt.insert(0, f"Instructions: {system_message}")
            
        return "\n\n".join(prompt) 
    
    async def get_available_models(self) -> Dict[str, dict]:
        """Get available models from provider."""
        if not self.available_models:
            try:
                self.available_models = await self._fetch_available_models()
            except Exception as e:
                logger.error(f"Error fetching models: {str(e)}")
                raise
        
        return self.available_models 