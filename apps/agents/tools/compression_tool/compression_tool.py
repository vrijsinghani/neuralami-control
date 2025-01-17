import os
from typing import Any, Type, List, Dict, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from apps.common.utils import get_llm, tokenize
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
import tiktoken
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)

class CompressionToolSchema(BaseModel):
    """Input schema for CompressionTool."""
    content: str = Field(..., description="The text content to process and organize")
    max_tokens: int = Field(default=16384, description="Maximum number of tokens in the processed output")
    detail_level: str = Field(
        default="comprehensive",
        description="Detail level: 'comprehensive' (preserve all details), 'detailed' (preserve most details), or 'focused' (key details only)"
    )

class CompressionTool(BaseTool):
    name: str = "Advanced Text Processing and Organization Tool"
    description: str = """
    Processes and organizes text content while preserving important information using advanced NLP techniques.
    Features semantic chunking, intelligent note-taking, and configurable detail levels.
    """
    args_schema: Type[BaseModel] = CompressionToolSchema
    
    modelname: str = Field(default=settings.SUMMARIZER)
    llm: Optional[Any] = Field(default=None)
    token_counter_callback: Optional[Any] = Field(default=None)
    tokenizer: Any = Field(default_factory=lambda: tiktoken.get_encoding("cl100k_base"))

    def __init__(self, **data):
        super().__init__(**data)
        self.llm, self.token_counter_callback = get_llm(self.modelname, temperature=0.0)

    def _create_semantic_chunks(self, content: str, chunk_size: int) -> List[str]:
        """Split content into semantic chunks using recursive character splitting."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=100,
            length_function=lambda x: len(self.tokenizer.encode(x)),
            separators=["\n\n", "\n", ". ", ", ", " "]
        )
        return splitter.split_text(content)

    def _get_processing_prompt(self, detail_level: str) -> str:
        """Get the appropriate processing prompt based on detail level."""
        prompts = {
            "comprehensive": """
            You are a meticulous note-taker with perfect recall. Your task is to process this text into detailed, organized notes:

            Guidelines:
            - Capture EVERY piece of information, no matter how small
            - Maintain all technical details, numbers, and specific examples
            - Preserve exact terminology and domain-specific language
            - Keep all dates, names, and references
            - Structure information in a clear, hierarchical format
            - Use bullet points and sub-bullets for organization
            - Remove ONLY exact duplicates of information
            - Keep all nuances and contextual details
            - Maintain the original meaning and implications
            - Include ALL supporting evidence and explanations
            
            Text to process:
            ```{content}```
            """,
            
            "detailed": """
            You are a thorough note-taker with excellent attention to detail. Your task is to process this text into well-organized notes:

            Guidelines:
            - Capture all significant information and supporting details
            - Maintain technical details and specific examples
            - Keep all important terminology and domain-specific language
            - Preserve relevant dates, names, and references
            - Structure information in a clear, logical format
            - Use bullet points and sub-bullets for organization
            - Remove only clearly redundant information
            - Maintain important nuances and context
            - Keep the original meaning and key implications
            - Include relevant supporting evidence
            
            Text to process:
            ```{content}```
            """,
            
            "focused": """
            You are a precise note-taker focusing on key information. Your task is to process this text into clear, focused notes:

            Guidelines:
            - Capture all key information and essential details
            - Maintain critical technical details and examples
            - Keep important terminology and specialized language
            - Preserve crucial dates, names, and references
            - Structure information in a clear, concise format
            - Use bullet points and sub-bullets for organization
            - Remove redundant information while keeping unique details
            - Maintain critical nuances and context
            - Preserve the core meaning and implications
            - Include key supporting evidence
            
            Text to process:
            ```{content}```
            """
        }
        return prompts.get(detail_level, prompts["comprehensive"])

    def _process_chunk(self, chunk: str, detail_level: str) -> str:
        """Process a single chunk of text into detailed notes."""
        process_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a detail-oriented note-taker who never loses information. Your notes should be thorough and well-organized."),
            ("human", self._get_processing_prompt(detail_level))
        ])
        
        process_chain = process_prompt | self.llm | StrOutputParser()
        return process_chain.invoke({'content': chunk})

    def _deduplicate_content(self, chunks: List[str]) -> List[str]:
        """Remove exact duplicates while preserving unique information."""
        dedup_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a detail-preserving content organizer. Your task is to:
            1. Identify and remove ONLY exact duplicates of information
            2. Preserve ALL unique details, even if similar
            3. Maintain ALL specific examples, numbers, and technical details
            4. Keep ALL contextual information and nuances
            5. Ensure no information is lost in the process
            6. Organize related information together logically
            """),
            ("human", "Text sections to organize:\n{chunks}")
        ])
        
        dedup_chain = dedup_prompt | self.llm | StrOutputParser()
        combined_chunks = "\n=====\n".join(chunks)
        result = dedup_chain.invoke({'chunks': combined_chunks})
        return result.split("\n=====\n")

    def _run(
        self,
        content: str,
        max_tokens: int = 16384,
        detail_level: str = "comprehensive",
        **kwargs: Any
    ) -> str:
        try:
            # Validate input
            if not content or not isinstance(content, str):
                return json.dumps({
                    "error": "Invalid input",
                    "message": "Content must be a non-empty string"
                })

            content_tokens = tokenize(content, self.tokenizer)
            logger.info(f"Original content tokens: {content_tokens}")

            if content_tokens <= max_tokens:
                processed_content = self._process_chunk(content, detail_level)
                final_tokens = tokenize(processed_content, self.tokenizer)
                logger.info(f"Processed content tokens (single chunk): {final_tokens}")
                return json.dumps({
                    "processed_content": processed_content,
                    "original_tokens": content_tokens,
                    "final_tokens": final_tokens,
                    "reduction_ratio": final_tokens / content_tokens,
                    "llm_input_tokens": self.token_counter_callback.input_tokens,
                    "llm_output_tokens": self.token_counter_callback.output_tokens
                })

            # Calculate chunk size based on max_tokens
            chunk_size = max_tokens 
            
            # Create semantic chunks
            chunks = self._create_semantic_chunks(content, chunk_size)
            logger.info(f"Created {len(chunks)} semantic chunks")
            
            # Process chunks
            processed_chunks = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                processed_chunk = self._process_chunk(chunk, detail_level)
                processed_chunks.append(processed_chunk)
                logger.info(f"Chunk {i+1} tokens: {tokenize(processed_chunk, self.tokenizer)}")
            
            # Deduplicate if needed
            if len(processed_chunks) > 1:
                logger.info("Deduplicating chunks")
                processed_chunks = self._deduplicate_content(processed_chunks)
            
            # Join chunks and check final token count
            processed_content = "\n\n".join(processed_chunks)
            final_tokens = tokenize(processed_content, self.tokenizer)
            logger.info(f"Final tokens after joining chunks: {final_tokens}")
            
            # If still too long, process again with focused detail level
            if final_tokens > max_tokens:
                logger.info("Performing second processing pass")
                processed_content = self._process_chunk(processed_content, "focused")
                final_tokens = tokenize(processed_content, self.tokenizer)
                logger.info(f"Final tokens after second pass: {final_tokens}")
            
            result = {
                "processed_content": processed_content,
                "original_tokens": content_tokens,
                "final_tokens": final_tokens,
                "reduction_ratio": final_tokens / content_tokens,
                "llm_input_tokens": self.token_counter_callback.input_tokens,
                "llm_output_tokens": self.token_counter_callback.output_tokens
            }
            
            # Reset the token counter for the next run
            self.token_counter_callback.input_tokens = 0
            self.token_counter_callback.output_tokens = 0
            
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error in CompressionTool: {str(e)}")
            return json.dumps({
                "error": "Processing failed",
                "message": str(e)
            })

