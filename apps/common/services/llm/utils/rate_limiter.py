"""Rate limiting utility for LLM providers."""

import time
from typing import Tuple

class RateLimiter:
    """Rate limiter for managing API request and token limits."""
    
    def __init__(
        self,
        provider_type: str,
        requests_per_minute: int = 60,
        tokens_per_minute: int = 40000
    ):
        self.provider_type = provider_type
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        
        # Initialize counters
        self.request_timestamps = []
        self.token_counts = []
        self.last_reset = time.time()
    
    def check_rate_limit(self) -> Tuple[bool, str]:
        """Check if current request is within rate limits."""
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        # Clean up old timestamps and counts
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > window_start]
        self.token_counts = self.token_counts[-self.requests_per_minute:]
        
        # Check request limit
        if len(self.request_timestamps) >= self.requests_per_minute:
            return False, "Request rate limit exceeded"
        
        # Check token limit
        tokens_used = sum(self.token_counts)
        if tokens_used >= self.tokens_per_minute:
            return False, "Token rate limit exceeded"
        
        return True, ""
    
    def increment_counters(self, tokens_used: int = 0):
        """Increment request and token counters."""
        current_time = time.time()
        
        # Reset counters if window has passed
        if current_time - self.last_reset >= 60:
            self.request_timestamps = []
            self.token_counts = []
            self.last_reset = current_time
        
        # Add new request
        self.request_timestamps.append(current_time)
        if tokens_used > 0:
            self.token_counts.append(tokens_used)
    
    def get_current_usage(self) -> Tuple[int, int]:
        """Get current request and token usage."""
        current_time = time.time()
        window_start = current_time - 60
        
        # Clean up old data
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > window_start]
        self.token_counts = self.token_counts[-self.requests_per_minute:]
        
        return len(self.request_timestamps), sum(self.token_counts) 