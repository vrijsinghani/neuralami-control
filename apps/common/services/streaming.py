"""
Streaming support for LLM responses.
"""

import logging
import asyncio
import json
from typing import AsyncGenerator, Optional, Any, Dict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class StreamingChunk:
    """Chunk of streaming response."""
    content: str
    metadata: Optional[Dict[str, Any]] = None
    delta_usage: Optional[Dict[str, int]] = None
    is_error: bool = False
    error_message: Optional[str] = None
    timestamp: datetime = datetime.now()

class StreamingManager:
    """Manager for streaming LLM responses."""
    
    def __init__(self, chunk_size: int = 100, timeout: int = 60):
        """
        Initialize streaming manager.
        
        Args:
            chunk_size: Size of chunks to buffer
            timeout: Streaming timeout in seconds
        """
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._buffer = []
    
    async def process_openai_stream(
        self,
        response_stream: Any
    ) -> AsyncGenerator[StreamingChunk, None]:
        """
        Process OpenAI streaming response.
        
        Args:
            response_stream: OpenAI streaming response
            
        Yields:
            StreamingChunk objects
        """
        try:
            async for chunk in response_stream:
                if hasattr(chunk.choices[0].delta, "content"):
                    content = chunk.choices[0].delta.content
                    if content:
                        yield StreamingChunk(
                            content=content,
                            metadata={'model': chunk.model},
                            delta_usage=chunk.usage.dict() if chunk.usage else None
                        )
        except Exception as e:
            logger.error(f"Error processing OpenAI stream: {str(e)}")
            yield StreamingChunk(
                content="",
                is_error=True,
                error_message=str(e)
            )
    
    async def process_anthropic_stream(
        self,
        response_stream: Any
    ) -> AsyncGenerator[StreamingChunk, None]:
        """
        Process Anthropic streaming response.
        
        Args:
            response_stream: Anthropic streaming response
            
        Yields:
            StreamingChunk objects
        """
        try:
            async for chunk in response_stream:
                if chunk.type == "content_block_delta":
                    yield StreamingChunk(
                        content=chunk.delta.text,
                        metadata={'model': chunk.model}
                    )
                elif chunk.type == "message_delta":
                    if chunk.usage:
                        yield StreamingChunk(
                            content="",
                            delta_usage={
                                'input_tokens': chunk.usage.input_tokens,
                                'output_tokens': chunk.usage.output_tokens
                            }
                        )
        except Exception as e:
            logger.error(f"Error processing Anthropic stream: {str(e)}")
            yield StreamingChunk(
                content="",
                is_error=True,
                error_message=str(e)
            )
    
    async def process_gemini_stream(
        self,
        response_stream: Any
    ) -> AsyncGenerator[StreamingChunk, None]:
        """
        Process Gemini streaming response.
        
        Args:
            response_stream: Gemini streaming response
            
        Yields:
            StreamingChunk objects
        """
        try:
            async for chunk in response_stream:
                if chunk.text:
                    yield StreamingChunk(
                        content=chunk.text,
                        metadata={'model': 'gemini-pro'}
                    )
        except Exception as e:
            logger.error(f"Error processing Gemini stream: {str(e)}")
            yield StreamingChunk(
                content="",
                is_error=True,
                error_message=str(e)
            )
    
    async def process_ollama_stream(
        self,
        response_stream: Any
    ) -> AsyncGenerator[StreamingChunk, None]:
        """
        Process Ollama streaming response.
        
        Args:
            response_stream: Ollama streaming response
            
        Yields:
            StreamingChunk objects
        """
        try:
            async for line in response_stream:
                try:
                    data = json.loads(line)
                    if 'response' in data:
                        yield StreamingChunk(
                            content=data['response'],
                            metadata={
                                'model': data.get('model', 'unknown'),
                                'eval_count': data.get('eval_count'),
                                'eval_duration': data.get('eval_duration')
                            }
                        )
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.error(f"Error processing Ollama stream: {str(e)}")
            yield StreamingChunk(
                content="",
                is_error=True,
                error_message=str(e)
            )
    
    async def buffer_stream(
        self,
        stream: AsyncGenerator[StreamingChunk, None]
    ) -> AsyncGenerator[str, None]:
        """
        Buffer streaming response into chunks.
        
        Args:
            stream: Stream of chunks
            
        Yields:
            Buffered content strings
        """
        try:
            async for chunk in stream:
                if chunk.is_error:
                    yield f"Error: {chunk.error_message}"
                    return
                
                self._buffer.append(chunk.content)
                
                if len(''.join(self._buffer)) >= self.chunk_size:
                    yield ''.join(self._buffer)
                    self._buffer = []
            
            # Yield remaining buffer
            if self._buffer:
                yield ''.join(self._buffer)
                self._buffer = []
                
        except asyncio.TimeoutError:
            logger.error("Streaming timeout")
            yield "Error: Streaming timeout"
        except Exception as e:
            logger.error(f"Error buffering stream: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def stream_with_timeout(
        self,
        stream: AsyncGenerator[StreamingChunk, None]
    ) -> AsyncGenerator[str, None]:
        """
        Stream with timeout.
        
        Args:
            stream: Stream of chunks
            
        Yields:
            Content with timeout handling
        """
        try:
            async with asyncio.timeout(self.timeout):
                async for content in self.buffer_stream(stream):
                    yield content
        except asyncio.TimeoutError:
            logger.error("Streaming timeout")
            yield "Error: Streaming timeout"
        except Exception as e:
            logger.error(f"Error in stream_with_timeout: {str(e)}")
            yield f"Error: {str(e)}" 