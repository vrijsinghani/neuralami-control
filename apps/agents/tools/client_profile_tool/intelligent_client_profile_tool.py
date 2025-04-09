# apps/agents/tools/client_profile_tool/intelligent_client_profile_tool.py

import logging
import json
import re
import time
import concurrent.futures
from urllib.parse import urljoin, urlparse
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from apps.agents.tools.website_distiller_tool.website_distiller_tool import WebsiteDistillerTool
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool
from apps.common.utils import get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from django.conf import settings
from django.core.exceptions import PermissionDenied
from markdown_it import MarkdownIt

# Import organization context utilities
from apps.organizations.utils import get_current_organization

# Import Client model - using Django's get_object_or_404 which is organization-aware
from django.shortcuts import get_object_or_404
from apps.seo_manager.models import Client

logger = logging.getLogger(__name__)

class IntelligentClientProfileToolSchema(BaseModel):
    """Input schema for IntelligentClientProfileTool."""
    client_id: int = Field(..., description="The ID of the client to generate a profile for")
    max_sitemap_urls: int = Field(default=100, description="Maximum number of URLs to retrieve from sitemap")
    max_selected_urls: int = Field(default=10, description="Maximum number of URLs to select for crawling")

    model_config = {
        "extra": "ignore"
    }

class IntelligentClientProfileTool(BaseTool):
    name: str = "Intelligent Client Profile Generator Tool"
    description: str = """
    Generates a comprehensive client profile by intelligently selecting and analyzing the most relevant pages from the client's website.
    This tool is organization-aware and can only access clients that the current user has permission to access.
    """
    args_schema: Type[BaseModel] = IntelligentClientProfileToolSchema

    def _analyze_homepage(self, website_url: str) -> Dict[str, Any]:
        """
        Analyze the homepage to extract content, metadata, and links.

        Args:
            website_url: The website URL to analyze

        Returns:
            Dictionary with homepage content, metadata, and links
        """
        logger.info(f"Analyzing homepage: {website_url}")

        # Import the adapter here to avoid circular imports
        from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter
        adapter = PlaywrightAdapter()

        try:
            # Fetch homepage with text, metadata, and links
            result = adapter.scrape(
                url=website_url,
                formats=["text", "metadata", "links"],
                timeout=60000,  # 60 seconds timeout
                stealth=True
            )

            if "error" in result:
                logger.error(f"Error analyzing homepage: {result.get('error')}")
                return {"error": result.get("error")}

            # Extract and clean the data
            homepage_data = {
                "url": website_url,
                "title": result.get("metadata", {}).get("title", ""),
                "description": result.get("metadata", {}).get("description", ""),
                "text": result.get("text", ""),
                "links": result.get("links", [])
            }

            # Filter links to only include internal links
            internal_links = []
            base_domain = urlparse(website_url).netloc

            for link in homepage_data["links"]:
                link_url = link.get("href", "")
                link_text = link.get("text", "")

                # Skip empty or javascript links
                if not link_url or link_url.startswith("javascript:") or link_url.startswith("#"):
                    continue

                # Handle relative URLs
                if not link_url.startswith("http"):
                    link_url = urljoin(website_url, link_url)

                # Check if it's an internal link
                link_domain = urlparse(link_url).netloc
                if link_domain == base_domain:
                    internal_links.append({
                        "url": link_url,
                        "text": link_text
                    })

            homepage_data["internal_links"] = internal_links
            logger.info(f"Successfully analyzed homepage with {len(internal_links)} internal links")
            return homepage_data

        except Exception as e:
            logger.error(f"Error analyzing homepage: {str(e)}")
            return {"error": str(e)}

    def _select_links_from_homepage(self, homepage_data: Dict[str, Any], client_name: str, max_urls: int = 10) -> List[str]:
        """
        Use LLM to select the most relevant links from the homepage.

        Args:
            homepage_data: Homepage analysis data
            client_name: Name of the client
            max_urls: Maximum number of URLs to select

        Returns:
            List of selected URLs
        """
        try:
            if "error" in homepage_data:
                logger.error(f"Cannot select links from homepage: {homepage_data.get('error')}")
                return []

            # Get internal links
            internal_links = homepage_data.get("internal_links", [])

            if not internal_links:
                logger.warning("No internal links found on homepage")
                return []

            # Prepare the prompt for the LLM
            model_name = settings.GENERAL_MODEL
            llm, _ = get_llm(model_name=model_name, temperature=0.0)

            # Create a prompt that asks the LLM to select the most relevant links
            link_selection_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are an AI assistant that helps select the most relevant links from a company's homepage to understand their business, products, services, and values."),
                ("human", """
                I need to create a comprehensive profile for a company called "{company_name}" with the website "{website_url}".

                I've analyzed their homepage and found the following information:

                Title: {homepage_title}
                Description: {homepage_description}

                Homepage Content Summary:
                {homepage_text_summary}

                Internal Links from Homepage:
                {internal_links_list}

                Based on this information, select the most relevant links (up to {max_urls}) that would help me understand:
                1. What the company does (products/services)
                2. Their mission, vision, and values
                3. Their target audience
                4. Their unique selling propositions
                5. Company history and background

                Please analyze these links and select the most relevant ones. Return ONLY a JSON array of the selected URLs, nothing else.
                Example response format: ["https://example.com/about", "https://example.com/services", ...]
                """)
            ])

            # Format the internal links for the prompt
            formatted_links = []
            for link in internal_links:
                url = link.get("url", "")
                text = link.get("text", "")
                formatted_links.append(f"- URL: {url}\n  Link Text: {text}")

            # Join the formatted links
            formatted_links_list = "\n\n".join(formatted_links)

            # Create a summary of the homepage text (first 1000 characters)
            homepage_text = homepage_data.get("text", "")
            homepage_text_summary = homepage_text[:1000] + "..." if len(homepage_text) > 1000 else homepage_text

            # Invoke the LLM
            response = llm.invoke(
                link_selection_prompt.format_messages(
                    company_name=client_name,
                    website_url=homepage_data.get("url", ""),
                    homepage_title=homepage_data.get("title", ""),
                    homepage_description=homepage_data.get("description", ""),
                    homepage_text_summary=homepage_text_summary,
                    internal_links_list=formatted_links_list,
                    max_urls=max_urls
                )
            )

            # Parse the response to extract the URLs
            try:
                # Try to find a JSON array in the response
                match = re.search(r'\[.*\]', response.content, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    selected_urls = json.loads(json_str)

                    # Validate the URLs
                    valid_urls = []
                    for url in selected_urls:
                        if isinstance(url, str) and url.startswith(('http://', 'https://')):
                            valid_urls.append(url)

                    # Limit to max_urls
                    valid_urls = valid_urls[:max_urls]

                    logger.info(f"Selected {len(valid_urls)} links from homepage")
                    return valid_urls
                else:
                    logger.warning("Could not find a JSON array in the LLM response")
                    return []
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing LLM response as JSON: {str(e)}")
                # Fallback: try to extract URLs using regex
                urls_in_response = re.findall(r'https?://[^\s\'"]+', response.content)

                # Filter to only include URLs that were in the original internal links
                original_urls = [link.get("url", "") for link in internal_links]
                valid_urls = [url for url in urls_in_response if url in original_urls][:max_urls]

                logger.info(f"Extracted {len(valid_urls)} URLs using regex fallback")
                return valid_urls

        except Exception as e:
            logger.error(f"Error selecting links from homepage: {str(e)}")
            return []

    def _select_relevant_urls(self, urls: List[str], website_url: str, client_name: str, max_urls: int = 10) -> List[str]:
        """
        Use LLM to select the most relevant URLs for understanding the company.

        Args:
            urls: List of URLs from sitemap
            website_url: Base website URL
            client_name: Name of the client
            max_urls: Maximum number of URLs to select

        Returns:
            List of selected URLs
        """
        try:
            # Filter out empty URLs
            url_list = [url for url in urls if url]

            if not url_list:
                logger.warning("No valid URLs found in sitemap")
                return []

            # Get metadata for the URLs
            urls_with_metadata = self._get_urls_with_metadata(url_list, website_url, max_urls=100)

            # Prepare the prompt for the LLM
            model_name = settings.GENERAL_MODEL
            llm, _ = get_llm(model_name=model_name, temperature=0.0)

            # Create a prompt that asks the LLM to select the most relevant URLs
            url_selection_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are an AI assistant that helps select the most relevant URLs from a website to understand a company's business, products, services, and values."),
                ("human", """
                I need to create a comprehensive profile for a company called "{company_name}" with the website "{website_url}".

                I have a list of URLs from their sitemap with their titles and descriptions. I need you to select the most relevant ones (up to {max_urls}) that would help me understand:
                1. What the company does (products/services)
                2. Their mission, vision, and values
                3. Their target audience
                4. Their unique selling propositions
                5. Company history and background

                Here are the URLs with their metadata:
                {url_metadata_list}

                Please analyze these URLs and select the most relevant ones. Return ONLY a JSON array of the selected URLs, nothing else.
                Example response format: ["https://example.com/about", "https://example.com/services", ...]
                """)
            ])

            # Format the URL list with metadata for the prompt
            formatted_url_metadata = []
            for item in urls_with_metadata:
                url = item.get("url", "")
                title = item.get("title", "")
                description = item.get("description", "")

                metadata_str = f"- URL: {url}"
                if title:
                    metadata_str += f"\n  Title: {title}"
                if description:
                    metadata_str += f"\n  Description: {description}"

                formatted_url_metadata.append(metadata_str)

            # Join the formatted metadata
            formatted_url_metadata_list = "\n\n".join(formatted_url_metadata)

            # Invoke the LLM
            response = llm.invoke(
                url_selection_prompt.format_messages(
                    company_name=client_name,
                    website_url=website_url,
                    max_urls=max_urls,
                    url_metadata_list=formatted_url_metadata_list
                )
            )

            # Parse the response to extract the URLs
            try:
                # Try to find a JSON array in the response
                match = re.search(r'\[.*\]', response.content, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    selected_urls = json.loads(json_str)

                    # Validate the URLs
                    valid_urls = []
                    for url in selected_urls:
                        if isinstance(url, str) and url.startswith(('http://', 'https://')):
                            valid_urls.append(url)

                    # Limit to max_urls
                    valid_urls = valid_urls[:max_urls]

                    logger.info(f"Selected {len(valid_urls)} URLs from sitemap")
                    return valid_urls
                else:
                    logger.warning("Could not find a JSON array in the LLM response")
                    return []
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing LLM response as JSON: {str(e)}")
                # Fallback: try to extract URLs using regex
                urls_in_response = re.findall(r'https?://[^\s\'"]+', response.content)
                valid_urls = [url for url in urls_in_response if url in url_list][:max_urls]
                logger.info(f"Extracted {len(valid_urls)} URLs using regex fallback")
                return valid_urls

        except Exception as e:
            logger.error(f"Error selecting relevant URLs: {str(e)}")
            return []

    def _fetch_urls_in_parallel(self, urls: List[str], max_workers: int = 5) -> Dict[str, Any]:
        """
        Fetch multiple URLs in parallel using a thread pool.

        Args:
            urls: List of URLs to fetch
            max_workers: Maximum number of parallel workers

        Returns:
            Dictionary with fetch results
        """
        results = []
        logger.info(f"Fetching {len(urls)} URLs in parallel with {max_workers} workers")

        # Import the adapter here to avoid circular imports
        from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter
        adapter = PlaywrightAdapter()

        def fetch_url(url):
            try:
                logger.info(f"Fetching URL: {url}")

                # Scrape the URL
                result = adapter.scrape(
                    url=url,
                    formats=["text", "metadata"],
                    timeout=60000,  # 60 seconds timeout
                    stealth=True
                )

                # Add URL to result if not already present
                if "url" not in result:
                    result["url"] = url

                # Check for errors
                if "error" not in result:
                    logger.info(f"Successfully fetched: {url}")
                    return result
                else:
                    logger.warning(f"Failed to fetch: {url} - {result.get('error')}")
                    return {"url": url, "error": result.get("error")}

            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                return {"url": url, "error": str(e)}

        # Use ThreadPoolExecutor to fetch URLs in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_url = {executor.submit(fetch_url, url): url for url in urls}

            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if "error" not in result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Exception processing result for {url}: {str(e)}")

        # Return the results
        return {
            "results": results,
            "status": "success" if results else "error",
            "message": f"Successfully fetched {len(results)} out of {len(urls)} URLs",
            "total_pages": len(results)
        }

    def _run(
        self,
        client_id: str,
        max_sitemap_urls: int = 100,
        max_selected_urls: int = 10,
    ) -> str:
        try:
            # Step 1: Get organization context and client info
            organization = get_current_organization()
            if not organization:
                return json.dumps({"error": "Organization context error", "message": "No active organization context found"})

            try:
                client = get_object_or_404(Client, id=client_id)
                client_name = client.name
                website_url = client.website_url

                if not website_url:
                    return json.dumps({
                        "error": "Missing website URL",
                        "message": f"Client {client_name} (ID: {client_id}) does not have a website URL"
                    })

                logger.info(f"Generating profile for client: {client_name}, website: {website_url}")
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

            # Step 2: Use the homepage analysis approach
            website_text = None
            approach_used = "homepage_analysis"
            metrics = {}

            try:
                # Analyze the homepage
                logger.info(f"Starting homepage analysis for {website_url}")
                homepage_data = self._analyze_homepage(website_url)

                if "error" not in homepage_data:
                    # Select relevant links from the homepage
                    selected_urls = self._select_links_from_homepage(
                        homepage_data=homepage_data,
                        client_name=client_name,
                        max_urls=max_selected_urls
                    )

                    if selected_urls:
                        # Fetch the selected URLs in parallel
                        fetch_result = self._fetch_urls_in_parallel(selected_urls)
                        results = fetch_result.get("results", [])

                        if results:
                            # Combine content from pages
                            combined_content = []

                            # First add the homepage content
                            homepage_title = homepage_data.get("title", "Homepage")
                            homepage_text = homepage_data.get("text", "")
                            if homepage_text:
                                combined_content.append(f"# {homepage_title}\n\n{homepage_text}\n\n")

                            # Then add content from other pages
                            for page in results:
                                title = page.get("metadata", {}).get("title", page.get("url", ""))
                                content = page.get("text", "")
                                if content:
                                    combined_content.append(f"# {title}\n\n{content}\n\n")

                            website_text = "\n".join(combined_content)
                            metrics = {
                                "homepage_links_found": len(homepage_data.get("internal_links", [])),
                                "urls_selected": len(selected_urls),
                                "urls_fetched": len(results)
                            }
                            logger.info(f"Successfully collected content from homepage and {len(results)} additional pages")
                else:
                    logger.warning(f"Homepage analysis failed: {homepage_data.get('error')}")
            except Exception as e:
                logger.warning(f"Homepage analysis approach failed: {str(e)}")

            # Step 3: Fall back to sitemap approach if homepage analysis failed
            if not website_text:
                logger.info("Homepage analysis failed, trying sitemap approach")
                approach_used = "sitemap"

                try:
                    # Get sitemap URLs
                    sitemap_tool = SitemapRetrieverTool()
                    sitemap_result = sitemap_tool._run(url=website_url, user_id=1, max_pages=max_sitemap_urls)
                    sitemap_urls = [url_dict.get("loc") for url_dict in sitemap_result.get("urls", []) if "loc" in url_dict]

                    if sitemap_result.get("success") and sitemap_urls:
                        # Select relevant URLs using metadata-enhanced selection
                        selected_urls = self._select_relevant_urls(
                            urls=sitemap_urls,
                            website_url=website_url,
                            client_name=client_name,
                            max_urls=max_selected_urls
                        )

                        if selected_urls:
                            # Fetch the selected URLs in parallel
                            fetch_result = self._fetch_urls_in_parallel(selected_urls)
                            results = fetch_result.get("results", [])

                            if results:
                                # Combine content from pages
                                combined_content = []
                                for page in results:
                                    title = page.get("metadata", {}).get("title", page.get("url", ""))
                                    content = page.get("text", "")
                                    if content:
                                        combined_content.append(f"# {title}\n\n{content}\n\n")

                                website_text = "\n".join(combined_content)
                                metrics = {
                                    "urls_found": len(sitemap_urls),
                                    "urls_selected": len(selected_urls),
                                    "urls_fetched": len(results)
                                }
                except Exception as e:
                    logger.warning(f"Sitemap approach failed: {str(e)}")

            # Step 4: Fall back to standard approach if needed
            if not website_text:
                logger.info("Using standard website distillation as fallback")
                approach_used = "standard"

                distiller = WebsiteDistillerTool()
                distilled_content = distiller._run(website_url=website_url)

                content_data = (
                    json.loads(distilled_content)
                    if isinstance(distilled_content, str)
                    else distilled_content
                )

                if "error" in content_data:
                    return json.dumps({
                        "error": "Content processing failed",
                        "message": content_data["message"]
                    })

                website_text = content_data.get("processed_content", "")

            if not website_text:
                return json.dumps({"error": "No content found", "message": "No content could be extracted"})

            # Step 4: Generate profile using LLM
            logger.info("Generating client profile")
            model_name = settings.GENERAL_MODEL
            llm, _ = get_llm(model_name=model_name, temperature=0.0)

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

            # Step 5: Return results
            result = {
                "success": True,
                "profile": profile_content,
                "profile_html": profile_content_html,
                "client_id": client_id,
                "client_name": client_name,
                "website_url": website_url,
                "organization_id": str(organization.id),
                "organization_name": organization.name,
                "website_text": website_text,
                "approach_used": approach_used
            }

            # Add metrics based on the approach used
            if metrics:
                result.update(metrics)

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error in IntelligentClientProfileTool: {str(e)}")
            return json.dumps({
                "error": "Profile generation failed",
                "message": str(e)
            })