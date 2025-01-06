from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
import json
import logging
from django.conf import settings
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from apps.common.utils import get_llm

logger = logging.getLogger(__name__)

class BusinessCredibilityToolSchema(BaseModel):
    """Input schema for BusinessCredibilityTool."""
    text_content: str = Field(..., description="The text content to analyze")
    html_content: str = Field(..., description="The HTML content to analyze")

class BusinessCredibilityTool(BaseTool):
    name: str = "Business Credibility Detector Tool"
    description: str = """
    Analyzes website content to detect business credibility signals including
    contact information, years in business, certifications, reviews, and services.
    """
    args_schema: Type[BaseModel] = BusinessCredibilityToolSchema

    def _run(
        self,
        text_content: str,
        html_content: str
    ) -> str:
        try:    
            # Get LLM
            llm, _ = get_llm(model_name=settings.GENERAL_MODEL, temperature=0.0)

            # Create prompt for credibility analysis
            expertise_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert business analyst detecting credibility signals from website content.
                Return your analysis as a clean JSON object without any markdown formatting."""),
                ("human", """
                Analyze the provided content for business credibility signals.
                Return a JSON object with two sections:
                1. credibility_signals: Dictionary of boolean indicators for each signal
                2. signal_details: Specific details found for each signal

                Focus on:
                - Business contact info (address, phone)
                - Years in business/establishment date
                - Customer reviews/testimonials
                - Services/products offered
                - Professional certifications/licenses

                Text Content:
                {text_content}

                HTML Content:
                {html_content}
                """)
            ])

            # Run analysis
            analysis_chain = expertise_prompt | llm | StrOutputParser()
            result = analysis_chain.invoke({
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
            
            logger.debug(f"Business credibility analysis result: {result}...")
            
            # Validate JSON before returning
            json.loads(result)  # This will raise an exception if invalid
            return result

        except Exception as e:
            logger.error(f"Error in BusinessCredibilityTool: {str(e)}")
            return json.dumps({
                "error": "Credibility analysis failed",
                "message": str(e)
            })
