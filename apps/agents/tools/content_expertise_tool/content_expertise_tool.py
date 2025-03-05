from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
import json
import logging
from django.conf import settings
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from apps.common.utils import get_llm

logger = logging.getLogger(__name__)

class ContentExpertiseToolSchema(BaseModel):
    """Input schema for ContentExpertiseTool."""
    text_content: str = Field(..., description="The text content to analyze")
    html_content: str = Field(..., description="The HTML content to analyze")
    content_type: str = Field(..., description="Type of content (blog, article, news)")
    url: str = Field(..., description="URL of the content")

class ContentExpertiseTool(BaseTool):
    name: str = "Content Expertise Detector Tool"
    description: str = """
    Analyzes content to detect expertise, authority, and trust signals including
    author expertise, content quality, citations, factual accuracy, and more.
    """
    args_schema: Type[BaseModel] = ContentExpertiseToolSchema

    def _run(
        self,
        text_content: str,
        html_content: str,
        content_type: str,
        url: str
    ) -> str:
        try:
            # Get LLM
            llm, _ = get_llm(model_name=settings.GENERAL_MODEL, temperature=0.0)

            # Create prompt for expertise analysis
            expertise_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert content analyst evaluating content quality and expertise signals.
                Return your analysis as a clean JSON object without any markdown formatting."""),
                ("human", """
                Analyze the provided content for expertise, authority, and trust signals.
                Return a JSON object with two sections:
                1. expertise_signals: Dictionary of boolean indicators for each signal
                2. signal_details: Specific details found for each signal

                Focus on:
                - Author Information (name, bio, credentials, links to profile)
                - Content Quality (depth, comprehensiveness, technical accuracy)
                - Citations and References (academic citations, expert quotes, data sources)
                - Factual Accuracy (fact-checking elements, source attribution)
                - Content Structure (organization, table of contents, section headers)
                - Topic Coverage (depth vs. superficial)
                - Schema Markup (Article, BlogPosting, NewsArticle)
                - Content Freshness (publish/update dates)
                
                Content Type: {content_type}
                URL: {url}
                
                Text Content:
                {text_content}
                
                HTML Content:
                {html_content}
                """)
            ])

            # Run analysis
            analysis_chain = expertise_prompt | llm | StrOutputParser()
            result = analysis_chain.invoke({
                "content_type": content_type,
                "url": url,
                "text_content": text_content,
                "html_content": html_content
            })
            
            # Clean the result of any markdown formatting
            result = result.strip()
            if result.startswith("```json"):
                result = result[7:]  # Remove ```json prefix
            if result.endswith("```"):
                result = result[:-3]  # Remove ``` suffix
            result = result.strip()
            
            logger.debug(f"Content expertise analysis result: {result[:200]}...")
            
            # Validate JSON before returning
            json.loads(result)  # This will raise an exception if invalid
            return result

        except Exception as e:
            logger.error(f"Error in ContentExpertiseTool: {str(e)}")
            return json.dumps({
                "error": "Expertise analysis failed",
                "message": str(e)
            }) 