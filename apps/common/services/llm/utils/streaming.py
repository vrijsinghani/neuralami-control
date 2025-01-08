"""Streaming utilities for LLM responses."""

import asyncio
from typing import AsyncGenerator, Any

class StreamingManager:
    """Manager for handling streaming responses from different providers."""
    
    def __init__(self, chunk_size: int = 100, timeout: int = 30):
        self.chunk_size = chunk_size
        self.timeout = timeout
    
    async def stream_with_timeout(
        self,
        stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[str, None]:
        """Stream with timeout handling."""
        try:
            async for chunk in stream:
                yield chunk
        except asyncio.TimeoutError:
            yield "Error: Stream timeout"
    
    async def process_openai_stream(
        self,
        response_stream: AsyncGenerator[Any, None]
    ) -> AsyncGenerator[str, None]:
        """Process OpenAI streaming response."""
        buffer = ""
        async for chunk in response_stream:
            if chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    buffer += content
                    if len(buffer) >= self.chunk_size:
                        yield buffer
                        buffer = ""
        if buffer:
            yield buffer
    
    async def process_anthropic_stream(
        self,
        response_stream: AsyncGenerator[Any, None]
    ) -> AsyncGenerator[str, None]:
        """Process Anthropic streaming response."""
        buffer = ""
        async for chunk in response_stream:
            if chunk.completion:
                buffer += chunk.completion
                if len(buffer) >= self.chunk_size:
                    yield buffer
                    buffer = ""
        if buffer:
            yield buffer
    
    async def process_gemini_stream(
        self,
        response_stream: AsyncGenerator[Any, None]
    ) -> AsyncGenerator[str, None]:
        """Process Gemini streaming response."""
        buffer = ""
        async for chunk in response_stream:
            if chunk.text:
                buffer += chunk.text
                if len(buffer) >= self.chunk_size:
                    yield buffer
                    buffer = ""
        if buffer:
            yield buffer
    
    async def process_ollama_stream(
        self,
        response_stream: AsyncGenerator[Any, None]
    ) -> AsyncGenerator[str, None]:
        """Process Ollama streaming response."""
        buffer = ""
        async for chunk in response_stream:
            if chunk.response:
                buffer += chunk.response
                if len(buffer) >= self.chunk_size:
                    yield buffer
                    buffer = ""
        if buffer:
            yield buffer 