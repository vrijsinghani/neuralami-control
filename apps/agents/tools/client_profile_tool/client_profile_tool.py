import logging
from typing import Type, Optional
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from apps.agents.tools.website_distiller_tool.website_distiller_tool import WebsiteDistillerTool
from apps.common.utils import get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
from django.conf import settings
from markdown_it import MarkdownIt


logger = logging.getLogger(__name__)

class ClientProfileToolSchema(BaseModel):
    """Input schema for ClientProfileTool."""
    website_url: str = Field(..., description="The website URL to analyze for profile generation")
    client_name: str = Field(..., description="The name of the client for logging purposes")

    model_config = {
        "extra": "ignore"
    }

class ClientProfileTool(BaseTool):
    name: str = "Client Profile Generator Tool"
    description: str = """
    Analyzes a website to generate a comprehensive client profile by crawling the site,
    processing its content, and using AI to create a structured profile.
    """
    args_schema: Type[BaseModel] = ClientProfileToolSchema

    def _run(
        self,
        website_url: str,
        client_name: str,
    ) -> str:
        try:
            # Step 1: Log the operation
            logger.info(f"Generating profile for client: {client_name} from website: {website_url}")
            
            # Step 2: Get website content using WebsiteDistillerTool
            logger.info(f"Getting website content for: {website_url}")
            distiller = WebsiteDistillerTool()
            distilled_content = distiller._run(website_url=website_url)
            
            if not distilled_content:
                return json.dumps({
                    "error": "Content extraction failed",
                    "message": "No content was retrieved from the website"
                })

            # Parse the distilled content
            content_data = json.loads(distilled_content)
            if "error" in content_data:
                return json.dumps({
                    "error": "Content processing failed",
                    "message": content_data["message"]
                })

            website_text = content_data.get("processed_content", "")

            # Step 3: Generate profile using LLM
            logger.info("Generating client profile")
            model_name=settings.GENERAL_MODEL
            llm, _ = get_llm(model_name=model_name,temperature=0.0)  # Lower temperature for more focused output

            profile_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a business analyst creating detailed company profiles."),
                ("human", """
                <context>
                {text}
                </context>

                Generate Company Profile - Process the provided website crawl data to create a comprehensive yet concise company profile suitable for use as background context for LLM agents. The profile should provide a detailed and accurate overview of the company, its operations, mission, values, target audience, and unique selling propositions (USPs). The information must be factual, objective, and readily usable.

                Specific Instructions:

                Key Information Extraction: Identify and extract crucial details from the website text, including:

                Company Mission and Vision: Summarize the company's mission statement and long-term vision.

                Products/Services: Provide a clear and concise description of the company's offerings, highlighting key features and benefits. Categorize and organize these effectively.

                Target Audience: Describe the company's ideal customer profile(s), including demographics, psychographics, and needs.

                Unique Selling Propositions (USPs): Identify what sets the company apart from competitors and articulates its value proposition to customers.

                Company History (optional): If available, include a brief overview of the company's history and milestones.

                Company Culture and Values (optional): If evident on the website, describe the company's culture and values. This might be inferred from its communication style and messaging.

                Brand Voice and Tone: Analyze the website's overall tone and writing style to determine the appropriate voice for future communications.

                Concise and Structured Output: The profile should be well-organized and easy to read, using clear headings and bullet points where appropriate to improve readability and usability for the subsequent writing agent. Avoid unnecessary details and focus on delivering crucial information efficiently.

                Factual Accuracy: Ensure all information is factual and accurately reflects the content of the provided website data.
                
                Refrain from appending commentary. Be pithy.
                
                """)
            ])

            profile_chain = profile_prompt | llm | StrOutputParser()
            profile_content = profile_chain.invoke({"text": website_text})

            # Generate HTML version of profile content
            md=MarkdownIt()
            profile_content_html = md.render(profile_content)
            
            return json.dumps({
                "success": True,
                "profile": profile_content,
                "profile_html": profile_content_html,
                "website_url": website_url,
                "client_name": client_name,
                "website_text": website_text  # Include the distilled content for saving at the view level
            })

        except Exception as e:
            logger.error(f"Error in ClientProfileTool: {str(e)}")
            return json.dumps({
                "error": "Profile generation failed",
                "message": str(e)
            })
