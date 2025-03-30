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
from django.core.exceptions import PermissionDenied
from markdown_it import MarkdownIt
from contextlib import contextmanager

# Import organization context utilities
from apps.organizations.utils import OrganizationContext, get_current_organization

# Import Client model - using Django's get_object_or_404 which you've modified to be organization-aware
from django.shortcuts import get_object_or_404
from apps.seo_manager.models import Client

logger = logging.getLogger(__name__)

class OrganizationAwareClientProfileToolSchema(BaseModel):
    """Input schema for OrganizationAwareClientProfileTool."""
    client_id: int = Field(..., description="The ID of the client to generate a profile for")

    model_config = {
        "extra": "ignore"
    }

class OrganizationAwareClientProfileTool(BaseTool):
    name: str = "Organization-Aware Client Profile Generator Tool"
    description: str = """
    Generates a comprehensive client profile by analyzing the client's website.
    This tool is organization-aware and can only access clients that the current user has permission to access.
    """
    args_schema: Type[BaseModel] = OrganizationAwareClientProfileToolSchema
    
    def _run(
        self,
        client_id: str,
    ) -> str:
        try:
            # Step 1: Log the operation start
            logger.info(f"Generating profile for client ID: {client_id}")
            
            # Step 2: Get the organization context
            organization = get_current_organization()
            if not organization:
                error_msg = "No active organization context found"
                logger.error(error_msg)
                return json.dumps({
                    "error": "Organization context error",
                    "message": error_msg
                })
            
            # Step 3: Get the client securely - this will automatically filter by organization
            # due to your organization-aware model managers and get_object_or_404 implementation
            try:
                client = get_object_or_404(Client, id=client_id)
                client_name = client.name
                website_url = client.website_url
                
                # Validate that we have a website URL
                if not website_url:
                    error_msg = f"Client {client_name} (ID: {client_id}) does not have a website URL"
                    logger.error(error_msg)
                    return json.dumps({
                        "error": "Missing website URL",
                        "message": error_msg
                    })
                
                logger.info(f"Retrieved client: {client_name}, website: {website_url}")
                
            except PermissionDenied:
                error_msg = f"Permission denied: You don't have access to client with ID {client_id}"
                logger.error(error_msg)
                return json.dumps({
                    "error": "Permission denied",
                    "message": error_msg
                })
            except Exception as e:
                error_msg = f"Error retrieving client with ID {client_id}: {str(e)}"
                logger.error(error_msg)
                return json.dumps({
                    "error": "Client retrieval error",
                    "message": error_msg
                })
            
            # Step 4: Get website content using WebsiteDistillerTool
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

            # Step 5: Generate profile using LLM
            logger.info("Generating client profile")
            model_name = settings.GENERAL_MODEL
            llm, _ = get_llm(model_name=model_name, temperature=0.0)  # Lower temperature for more focused output

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
            md = MarkdownIt()
            profile_content_html = md.render(profile_content)
            
            # Return the profile with client and organization context
            return json.dumps({
                "success": True,
                "profile": profile_content,
                "profile_html": profile_content_html,
                "client_id": client_id,
                "client_name": client_name,
                "website_url": website_url,
                "organization_id": str(organization.id),
                "organization_name": organization.name,
                "website_text": website_text  # Include the distilled content for saving at the view level
            })

        except Exception as e:
            logger.error(f"Error in OrganizationAwareClientProfileTool: {str(e)}")
            return json.dumps({
                "error": "Profile generation failed",
                "message": str(e)
            })
