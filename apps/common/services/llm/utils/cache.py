"""Caching utility for LLM responses."""

import json
import time
from typing import Any, Dict, Optional, Tuple

class LLMCache:
    """Cache for LLM responses."""
    
    def __init__(self, ttl: int = 3600):
        self.ttl = ttl
        self.cache = {}
        self.hits = 0
        self.misses = 0
    
    def _get_cache_key(self, messages: list, provider_type: str, model: str, **kwargs) -> str:
        """Generate cache key from request parameters."""
        key_data = {
            'messages': messages,
            'provider': provider_type,
            'model': model,
            **kwargs
        }
        return json.dumps(key_data, sort_keys=True)
    
    def get_cached_response(
        self,
        messages: list,
        provider_type: str,
        model: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired."""
        key = self._get_cache_key(messages, provider_type, model, **kwargs)
        
        if key in self.cache:
            cached = self.cache[key]
            if time.time() - cached['timestamp'] < self.ttl:
                self.hits += 1
                return cached
            else:
                del self.cache[key]
        
        self.misses += 1
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
        """Cache a response."""
        key = self._get_cache_key(messages, provider_type, model, **kwargs)
        self.cache[key] = {
            'content': content,
            'metadata': metadata,
            'timestamp': time.time()
        }
    
    def get_cache_stats(self) -> Tuple[int, int]:
        """Get cache hit/miss statistics."""
        return self.hits, self.misses
    
    def clear(self):
        """Clear the cache."""
        self.cache = {}
        self.hits = 0
        self.misses = 0 