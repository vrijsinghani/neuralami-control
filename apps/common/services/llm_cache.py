"""
Caching service for LLM responses.
"""

import logging
import hashlib
import json
from typing import Optional, Any, Tuple
from django.core.cache import cache
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class CachedResponse:
    """Cached LLM response."""
    content: str
    metadata: dict
    created_at: datetime
    provider_type: str
    model: str

class LLMCache:
    """Cache for LLM responses."""
    
    def __init__(self, ttl: int = 3600):
        """
        Initialize cache.
        
        Args:
            ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.ttl = ttl
        self.cache_key_prefix = "llm_cache"
    
    def _generate_cache_key(self, messages: list, provider_type: str, model: str, **kwargs) -> str:
        """Generate cache key from request parameters."""
        # Create deterministic string from parameters
        cache_data = {
            'messages': messages,
            'provider_type': provider_type,
            'model': model,
            # Include relevant kwargs that affect output
            'temperature': kwargs.get('temperature', 0.7),
            'max_tokens': kwargs.get('max_tokens'),
            'top_p': kwargs.get('top_p', 1.0),
        }
        
        # Create hash of parameters
        cache_str = json.dumps(cache_data, sort_keys=True)
        key_hash = hashlib.sha256(cache_str.encode()).hexdigest()
        
        return f"{self.cache_key_prefix}:{provider_type}:{model}:{key_hash}"
    
    def get_cached_response(
        self,
        messages: list,
        provider_type: str,
        model: str,
        **kwargs
    ) -> Optional[CachedResponse]:
        """
        Get cached response if available.
        
        Args:
            messages: List of messages
            provider_type: Provider type
            model: Model name
            **kwargs: Additional parameters
            
        Returns:
            Cached response if available, None otherwise
        """
        key = self._generate_cache_key(messages, provider_type, model, **kwargs)
        cached = cache.get(key)
        
        if cached:
            logger.debug(f"Cache hit for {provider_type}/{model}")
            return CachedResponse(**cached)
        
        return None
    
    def cache_response(
        self,
        messages: list,
        provider_type: str,
        model: str,
        content: str,
        metadata: dict,
        **kwargs
    ):
        """
        Cache LLM response.
        
        Args:
            messages: List of messages
            provider_type: Provider type
            model: Model name
            content: Response content
            metadata: Response metadata
            **kwargs: Additional parameters
        """
        key = self._generate_cache_key(messages, provider_type, model, **kwargs)
        
        cached_response = CachedResponse(
            content=content,
            metadata=metadata,
            created_at=datetime.now(),
            provider_type=provider_type,
            model=model
        )
        
        # Cache with TTL
        cache.set(key, cached_response.__dict__, timeout=self.ttl)
        logger.debug(f"Cached response for {provider_type}/{model}")
    
    def invalidate_cache(
        self,
        messages: list,
        provider_type: str,
        model: str,
        **kwargs
    ):
        """
        Invalidate cached response.
        
        Args:
            messages: List of messages
            provider_type: Provider type
            model: Model name
            **kwargs: Additional parameters
        """
        key = self._generate_cache_key(messages, provider_type, model, **kwargs)
        cache.delete(key)
        logger.debug(f"Invalidated cache for {provider_type}/{model}")
    
    def get_cache_stats(self) -> Tuple[int, int]:
        """
        Get cache statistics.
        
        Returns:
            Tuple of (hits, misses)
        """
        stats = cache.get_stats()
        return stats.get('hits', 0), stats.get('misses', 0) 