"""Base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

from apps.common.models import LLMConfiguration

class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize base provider with configuration."""
        self.config = config
        self.model_name = config.default_model
        self.max_output_tokens = 1000
        self.temperature = 0.7
        self.available_models = {}
    
    @abstractmethod
    async def initialize(self):
        """Initialize provider and fetch available models."""
        pass
    
    @abstractmethod
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion from provider."""
        pass
    
    @abstractmethod
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings from provider."""
        pass
    
    async def get_available_models(self) -> Dict[str, dict]:
        """Get available models from provider."""
        return self.available_models 