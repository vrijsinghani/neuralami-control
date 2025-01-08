"""Core LLM service implementation."""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Tuple, Union
import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential

from django.conf import settings
from apps.common.models import LLMConfiguration, TokenUsage, ProviderType

from .providers.base import BaseLLMProvider
from .providers.gemini import GeminiProvider
from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.openrouter import OpenRouterProvider
from .providers.ollama import OllamaProvider
from .utils.cache import LLMCache
from .utils.rate_limiter import RateLimiter
from .utils.streaming import StreamingManager

logger = logging.getLogger(__name__)

class LLMService:
    """
    Centralized service for managing LLM interactions.
    Handles model initialization, authentication, token tracking, and error handling.
    """
    
    PROVIDER_MAP = {
        'gemini': GeminiProvider,
        'openai': OpenAIProvider,
        'anthropic': AnthropicProvider,
        'openrouter': OpenRouterProvider,
        'ollama': OllamaProvider
    }
    
    def __init__(self, user=None, cache_ttl: int = 3600):
        """Initialize the LLM service with optional user context."""
        self.user = user
        self._provider_instances: Dict[str, BaseLLMProvider] = {}
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Initialize cache
        self.cache = LLMCache(ttl=cache_ttl)
        
        # Initialize config
        self._config = None
        self._config_task = None
    
    @property
    async def config(self) -> Optional[LLMConfiguration]:
        """Get the active LLM configuration."""
        if self._config is None and not self._config_task:
            self._config_task = asyncio.create_task(self._load_config())
        if self._config_task:
            await self._config_task
        return self._config
        
    async def _load_config(self):
        """Load the configuration for the specified provider type."""
        try:
            # Get the most recently updated configuration for each provider type
            self._config = await LLMConfiguration.objects.order_by('-updated_at').afirst()
            if not self._config:
                logger.warning("No LLM configuration found")
        except Exception as e:
            logger.error(f"Error loading LLM configuration: {str(e)}")
            self._config = None
        finally:
            self._config_task = None
    
    async def get_provider(
        self,
        provider_type: str = "gemini",
        **kwargs
    ) -> BaseLLMProvider:
        """Get or create a provider instance."""
        # Get configuration matching provider type
        from django.db import models
        config = await models.QuerySet(LLMConfiguration).filter(provider_type=provider_type).afirst()
        if not config:
            raise ValueError(f"No configuration found for provider type: {provider_type}")
            
        cache_key = f"{provider_type}_{config.name}"
        
        if cache_key in self._provider_instances:
            return self._provider_instances[cache_key]
        
        provider_class = self.PROVIDER_MAP.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unsupported provider type: {provider_type}")
        
        provider = provider_class(config)
        
        # Initialize provider if it has initialize method
        if hasattr(provider, 'initialize'):
            try:
                await provider.initialize()
            except Exception as e:
                logger.error(f"Error initializing provider {provider_type}: {str(e)}")
                raise
        
        self._provider_instances[cache_key] = provider
        return provider
    
    async def _get_rate_limiter(self, provider_type: str) -> RateLimiter:
        """Get or create rate limiter for provider."""
        if provider_type not in self._rate_limiters:
            from django.db import models
            config = await models.QuerySet(LLMConfiguration).filter(provider_type=provider_type).afirst()
            if not config:
                raise ValueError(f"No configuration found for provider type: {provider_type}")
                
            self._rate_limiters[provider_type] = RateLimiter(
                provider_type=provider_type,
                requests_per_minute=config.requests_per_minute,
                tokens_per_minute=config.tokens_per_minute
            )
        return self._rate_limiters[provider_type]
    
    async def get_available_models(self, provider_type: str) -> dict:
        """Get available models for a provider."""
        provider = await self.get_provider(provider_type)
        models = await provider.get_available_models()
        
        # If models is empty or None, try initializing the provider again
        if not models:
            try:
                await provider.initialize()
                models = provider.available_models
            except Exception as e:
                logger.error(f"Error getting models after reinitialization: {str(e)}")
                raise
        
        return models
    
    async def get_provider_config(self, provider_type: str) -> Optional[LLMConfiguration]:
        """Get configuration for a specific provider type."""
        try:
            return await LLMConfiguration.objects.filter(
                provider_type=provider_type
            ).order_by('-updated_at').afirst()
        except Exception as e:
            logger.error(f"Error getting provider config: {str(e)}")
            return None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry_error_callback=lambda retry_state: retry_state.outcome.result()
    )
    async def get_completion(
        self,
        messages: list,
        provider_type: str = None,
        use_cache: bool = True,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[str, None]]:
        """
        Get completion from the configured provider with caching and rate limiting.
        
        Args:
            messages: List of messages for the completion
            provider_type: Type of provider to use (required)
            use_cache: Whether to use response caching
            stream: Whether to stream the response
            **kwargs: Additional completion parameters
            
        Returns:
            Either (completion text, metadata) tuple or streaming generator
        """
        if stream:
            return self.get_streaming_completion(
                messages=messages,
                provider_type=provider_type,
                **kwargs
            )
        
        if not provider_type:
            raise ValueError("provider_type is required")
            
        config = await self.get_provider_config(provider_type)
        if not config:
            raise ValueError(f"No configuration found for provider type: {provider_type}")
        
        provider_type = provider_type or config.provider_type
        model = kwargs.get('model_name', config.default_model)
        
        # Check cache if enabled
        if use_cache:
            cached = self.cache.get_cached_response(
                messages=messages,
                provider_type=provider_type,
                model=model,
                **kwargs
            )
            if cached:
                return cached.content, cached.metadata
        
        # Check rate limits
        rate_limiter = await self._get_rate_limiter(provider_type)
        is_allowed, reason = rate_limiter.check_rate_limit()
        if not is_allowed:
            raise ValueError(f"Rate limit exceeded: {reason}")
        
        # Get provider
        provider = await self.get_provider(provider_type)
        
        try:
            # Get completion from provider
            completion, metadata = await provider.get_completion(
                messages=messages,
                stream=False,
                **kwargs
            )
            
            # Track token usage
            if 'usage' in metadata:
                self.track_token_usage(
                    model=model,
                    prompt_tokens=metadata['usage'].get('prompt_tokens', 0),
                    completion_tokens=metadata['usage'].get('completion_tokens', 0),
                    provider_type=provider_type
                )
                rate_limiter.increment_counters(
                    tokens_used=metadata['usage'].get('total_tokens', 0)
                )
            
            # Cache response if enabled
            if use_cache:
                self.cache.cache_response(
                    messages=messages,
                    provider_type=provider_type,
                    model=model,
                    content=completion,
                    metadata=metadata,
                    **kwargs
                )
            
            return completion, metadata
            
        except Exception as e:
            logger.error(f"Error in completion: {str(e)}")
            
            # Try fallback provider if configured
            if config.fallback_provider:
                logger.info(f"Attempting fallback to {config.fallback_provider.provider_type}")
                return await self.get_completion(
                    messages=messages,
                    provider_type=config.fallback_provider.provider_type,
                    use_cache=use_cache,
                    **kwargs
                )
            
            raise
    
    async def get_streaming_completion(
        self,
        messages: list,
        provider_type: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Get streaming completion from the configured provider.
        
        Args:
            messages: List of messages for the completion
            provider_type: Type of provider to use (defaults to config's provider_type)
            **kwargs: Additional completion parameters
            
        Yields:
            Chunks of completion text
        """
        config = await self.config
        if not config:
            raise ValueError("No active LLM configuration found")
        
        provider_type = provider_type or config.provider_type
        model = kwargs.get('model_name', config.default_model)
        
        # Check rate limits
        rate_limiter = await self._get_rate_limiter(provider_type)
        is_allowed, reason = rate_limiter.check_rate_limit()
        if not is_allowed:
            raise ValueError(f"Rate limit exceeded: {reason}")
        
        # Get provider and streaming manager
        provider = await self.get_provider(provider_type)
        streaming_config = config.get_streaming_config()
        streaming_manager = StreamingManager(
            chunk_size=streaming_config['stream_chunk_size'],
            timeout=streaming_config['stream_timeout']
        )
        
        try:
            # Set streaming flag in kwargs
            kwargs['stream'] = True
            
            # Get streaming response from provider
            response_stream = await provider.get_completion(messages, **kwargs)
            
            # Process stream based on provider type
            if provider_type == ProviderType.OPENAI:
                chunk_stream = streaming_manager.process_openai_stream(response_stream)
            elif provider_type == ProviderType.ANTHROPIC:
                chunk_stream = streaming_manager.process_anthropic_stream(response_stream)
            elif provider_type == ProviderType.GEMINI:
                chunk_stream = streaming_manager.process_gemini_stream(response_stream)
            elif provider_type == ProviderType.OLLAMA:
                chunk_stream = streaming_manager.process_ollama_stream(response_stream)
            else:
                raise ValueError(f"Streaming not supported for provider: {provider_type}")
            
            # Stream with timeout
            async for content in streaming_manager.stream_with_timeout(chunk_stream):
                yield content
            
        except Exception as e:
            logger.error(f"Error in streaming completion: {str(e)}")
            
            # Try fallback provider if configured
            if config.fallback_provider:
                logger.info(f"Attempting fallback to {config.fallback_provider.provider_type}")
                async for content in self.get_streaming_completion(
                    messages=messages,
                    provider_type=config.fallback_provider.provider_type,
                    **kwargs
                ):
                    yield content
            else:
                yield f"Error: {str(e)}"
    
    def track_token_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider_type: str = None
    ):
        """Track token usage in database."""
        try:
            TokenUsage.objects.create(
                user=self.user,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                provider_type=provider_type or self.config.provider_type,
                request_type='completion'
            )
        except Exception as e:
            logger.error(f"Error tracking token usage: {str(e)}")
    
    async def validate_api_key(self) -> bool:
        """Validate the current API key configuration."""
        config = await self.config
        if not config:
            return False
            
        try:
            # Try a simple completion request to validate
            messages = [{"role": "user", "content": "test"}]
            await self.get_completion(messages, use_cache=False)
            return True
        except Exception as e:
            logger.error(f"API key validation failed: {str(e)}")
            return False 