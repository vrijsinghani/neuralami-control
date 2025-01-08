from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
import json
import logging
from django.conf import settings
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from apps.common.utils import get_llm
import re
from bs4 import BeautifulSoup

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

    def _preprocess_content(self, text_content: str, html_content: str) -> Dict[str, Any]:
        """Pre-process content to detect common business information patterns."""
        # Phone number patterns
        phone_patterns = [
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # 123-456-7890 or 1234567890
            r'\(\d{3}\)\s*\d{3}[-.]?\d{4}',     # (123) 456-7890
            r'\b\d{3}\s+\d{3}\s+\d{4}\b'        # 123 456 7890
        ]
        
        # Address patterns
        address_patterns = [
            r'\d+\s+[A-Za-z0-9\s,]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Trail|Trl|Highway|Hwy|Route|Rte)[,.\s]+(?:[A-Za-z\s]+,\s*)?[A-Z]{2}\s+\d{5}(?:-\d{4})?',
            r'\d+\s+[A-Za-z\s]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Trail|Trl|Highway|Hwy|Route|Rte)'
        ]
        
        # Business hours patterns
        hours_patterns = [
            r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*(?:day)?[-:\s]+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)[-\s]+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))',
            r'\b(?:\d{1,2}:\d{2}|(?:1[0-2]|0?[1-9])(?::\d{2})?\s*(?:am|pm|AM|PM))[-\s]+(?:\d{1,2}:\d{2}|(?:1[0-2]|0?[1-9])(?::\d{2})?\s*(?:am|pm|AM|PM))'
        ]

        # Initialize results
        results = {
            "has_phone": False,
            "has_address": False,
            "has_hours": False,
            "found_patterns": {
                "phones": [],
                "addresses": [],
                "hours": []
            }
        }

        # Check footer and contact sections first
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            footer = soup.find('footer')
            contact_section = soup.find(id=lambda x: x and 'contact' in x.lower()) or \
                            soup.find(class_=lambda x: x and 'contact' in x.lower())
            
            priority_sections = []
            if footer:
                priority_sections.append(footer.get_text())
            if contact_section:
                priority_sections.append(contact_section.get_text())
            
            # Check priority sections first
            for section in priority_sections:
                # Check phone patterns
                for pattern in phone_patterns:
                    phones = re.findall(pattern, section)
                    if phones:
                        results["has_phone"] = True
                        results["found_patterns"]["phones"].extend(phones)
                
                # Check address patterns
                for pattern in address_patterns:
                    addresses = re.findall(pattern, section)
                    if addresses:
                        results["has_address"] = True
                        results["found_patterns"]["addresses"].extend(addresses)
                
                # Check hours patterns
                for pattern in hours_patterns:
                    hours = re.findall(pattern, section)
                    if hours:
                        results["has_hours"] = True
                        results["found_patterns"]["hours"].extend(hours)

        # If not found in priority sections, check entire content
        if not (results["has_phone"] and results["has_address"] and results["has_hours"]):
            # Check phone patterns
            for pattern in phone_patterns:
                phones = re.findall(pattern, text_content)
                if phones:
                    results["has_phone"] = True
                    results["found_patterns"]["phones"].extend(phones)
            
            # Check address patterns
            for pattern in address_patterns:
                addresses = re.findall(pattern, text_content)
                if addresses:
                    results["has_address"] = True
                    results["found_patterns"]["addresses"].extend(addresses)
            
            # Check hours patterns
            for pattern in hours_patterns:
                hours = re.findall(pattern, text_content)
                if hours:
                    results["has_hours"] = True
                    results["found_patterns"]["hours"].extend(hours)

        # Remove duplicates
        results["found_patterns"]["phones"] = list(set(results["found_patterns"]["phones"]))
        results["found_patterns"]["addresses"] = list(set(results["found_patterns"]["addresses"]))
        results["found_patterns"]["hours"] = list(set(results["found_patterns"]["hours"]))

        return results

    def _run(
        self,
        text_content: str,
        html_content: str
    ) -> str:
        try:    
            # Pre-process content for business info
            preprocessed = self._preprocess_content(text_content, html_content)
            
            # If we found business info through regex, we can skip the LLM for this part
            if preprocessed["has_phone"] or preprocessed["has_address"] or preprocessed["has_hours"]:
                has_business_info = True
                business_info_details = preprocessed["found_patterns"]
            else:
                has_business_info = False
                business_info_details = {}

            # Get LLM for other credibility signals
            llm, _ = get_llm(model_name=settings.GENERAL_MODEL, temperature=0.0)

            # Create prompt for credibility analysis
            expertise_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert business analyst detecting credibility signals from website content.
                Pay special attention to footer sections, contact pages, and about sections where business information is typically located.
                Return your analysis as a clean JSON object without any markdown formatting."""),
                ("human", """
                Analyze the provided content for business credibility signals.
                Focus on these signals (ignore business contact info as it's handled separately):
                - Years in business/establishment date
                - Customer reviews/testimonials
                - Services/products offered
                - Professional certifications/licenses

                Return a JSON object with:
                1. credibility_signals: Dictionary of boolean indicators for each signal
                2. signal_details: Specific details found for each signal

                Text Content:
                {text_content}

                HTML Content:
                {html_content}
                """)
            ])

            # Run analysis for other signals
            other_signals = analysis_chain = expertise_prompt | llm | StrOutputParser()
            other_signals_result = other_signals.invoke({
                "text_content": text_content,
                "html_content": html_content
            })
            
            # Clean the result of any markdown formatting
            other_signals_result = other_signals_result.strip()
            if other_signals_result.startswith("```json"):
                other_signals_result = other_signals_result[7:]
            if other_signals_result.endswith("```"):
                other_signals_result = other_signals_result[:-3]
            other_signals_result = other_signals_result.strip()
            
            # Parse other signals result
            other_signals_data = json.loads(other_signals_result)
            
            # Combine results
            final_result = {
                "credibility_signals": {
                    "business_info": has_business_info,
                    **other_signals_data.get("credibility_signals", {})
                },
                "signal_details": {
                    "business_info": business_info_details if has_business_info else None,
                    **other_signals_data.get("signal_details", {})
                }
            }
            
            logger.debug(f"Business credibility analysis result: {json.dumps(final_result)[:200]}...")
            return json.dumps(final_result)

        except Exception as e:
            logger.error(f"Error in BusinessCredibilityTool: {str(e)}")
            return json.dumps({
                "error": "Credibility analysis failed",
                "message": str(e)
            })
