"""
Rate limiter service for LLM requests.
"""

import time
import logging
from typing import Optional, Tuple
from django.core.cache import cache
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class RateLimitInfo:
    """Rate limit information."""
    window_start: float
    request_count: int
    token_count: int

class RateLimiter:
    """Rate limiter for LLM requests."""
    
    def __init__(self, provider_type: str, requests_per_minute: int, tokens_per_minute: int):
        self.provider_type = provider_type
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self.cache_key_prefix = f"ratelimit:{provider_type}"
    
    def _get_window_key(self) -> str:
        """Get cache key for current minute window."""
        return f"{self.cache_key_prefix}:{int(time.time() / 60)}"
    
    def _get_rate_limit_info(self) -> RateLimitInfo:
        """Get current rate limit information."""
        key = self._get_window_key()
        info = cache.get(key)
        if not info:
            info = RateLimitInfo(
                window_start=time.time(),
                request_count=0,
                token_count=0
            )
        return info
    
    def _save_rate_limit_info(self, info: RateLimitInfo):
        """Save rate limit information."""
        key = self._get_window_key()
        # Save with TTL of 2 minutes to ensure cleanup
        cache.set(key, info, timeout=120)
    
    def check_rate_limit(self, estimated_tokens: Optional[int] = None) -> Tuple[bool, str]:
        """
        Check if request is within rate limits.
        
        Args:
            estimated_tokens: Estimated token count for request
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        info = self._get_rate_limit_info()
        
        # Check request limit
        if info.request_count >= self.requests_per_minute:
            return False, f"Request limit of {self.requests_per_minute}/min exceeded"
        
        # Check token limit if provided
        if estimated_tokens and info.token_count + estimated_tokens > self.tokens_per_minute:
            return False, f"Token limit of {self.tokens_per_minute}/min exceeded"
        
        return True, ""
    
    def increment_counters(self, tokens_used: Optional[int] = None):
        """
        Increment request and token counters.
        
        Args:
            tokens_used: Number of tokens used in request
        """
        info = self._get_rate_limit_info()
        info.request_count += 1
        if tokens_used:
            info.token_count += tokens_used
        self._save_rate_limit_info(info)
    
    def get_current_usage(self) -> Tuple[int, int]:
        """
        Get current usage counts.
        
        Returns:
            Tuple of (requests_used, tokens_used)
        """
        info = self._get_rate_limit_info()
        return info.request_count, info.token_count 