import os
from typing import Any, Type, List, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from apps.agents.tools.searxng_tool.searxng_tool import SearxNGSearchTool
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.common.utils import get_llm as utils_get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from django.conf import settings
import json
import logging
from celery.exceptions import Ignore
from datetime import datetime

logger = logging.getLogger(__name__)
# DO NOT REMOVE BELOW COMMENTS - FOR USE LATER
# You are an expert in information retrieval and research strategy.  You are assisting a user who is using a tool called the "DeepResearchTool". This tool performs web research based on a user's query. It has two key parameters:

# *   **`breadth` (integer, 2-10):** Controls the number of different search queries generated at each step.  Higher breadth means more diverse initial searches.
# *   **`depth` (integer, 1-5):** Controls the number of recursive research iterations.  Higher depth means more in-depth follow-up on initial results.

# The user provides a research query.  Your task is to analyze the query and recommend appropriate values for `breadth` and `depth`.  Consider the following:

# **Factors for `breadth`:**

# *   **Query Complexity:** How broad or narrow is the topic? Broader topics need higher breadth.
# *   **Synonyms/Variations:** How many different ways could the query be phrased? More variations suggest higher breadth.
# *   **Exhaustiveness:** Does the user need a comprehensive list ("find all...") or a focused set of results? Comprehensive needs higher breadth.
# *   **Subtopics:** Are there multiple related subtopics to explore?  If so, higher breadth.
# *   **Specificity:** How specific are the search terms. More specific terms generally suggest lower breadth.

# **Factors for `depth`:**

# *   **Layered Information:** Are there multiple layers of information (e.g., find a list, then explore items on that list)? If so, higher depth.
# *   **Context/Background:** Does the user need to understand the context around the results, or just find the results?  Context requires higher depth.
# *   **Discovery vs. Verification:** Is the goal to discover new information (higher depth) or verify existing information (lower depth)?
# *   **Refinement:** Are follow-up queries likely needed to refine the initial results? If so, higher depth.
# *   **Direct Answers:** Is a simple, direct answer possible (lower depth), or will deeper investigation be required (higher depth).

# **Output Format:**

# Provide your recommendations in the following JSON format:

# ```json
# {
#   "query": "[User's Query Here]",
#   "recommended_breadth": [Integer Value],
#   "recommended_depth": [Integer Value],
#   "reasoning": "[Concise explanation of your choices, referencing the factors above]"
# }
# Log settings at module level
logger.info(f"Module level - GENERAL_MODEL from settings: {settings.GENERAL_MODEL}")

class DeepResearchToolSchema(BaseModel):
    """Input schema for DeepResearchTool."""

    class Config:
        """Pydantic config"""
        use_enum_values = True
        extra = "forbid"
        json_schema_extra = {
            "examples": [
                {
                    "query": "What are the latest developments in quantum computing?",
                    "breadth": 4,
                    "depth": 2,
                    "user_id": 1
                }
            ]
        }

    query: str = Field(
        ...,
        description="The query to research deeply.",
        examples=["What are the latest developments in quantum computing?"]
    )
    breadth: int = Field(
        ...,
        description="Number of parallel search queries to make (recommended 2-10)",
        ge=2,
        le=10,
        examples=[4]
    )
    depth: int = Field(
        ...,
        description="Number of recursive research iterations (recommended 1-5)",
        ge=1,
        le=5,
        examples=[2]
    )
    user_id: int = Field(
        ...,
        description="ID of the user initiating the research"
    )

class DeepResearchTool(BaseTool):
    name: str = "Deep Research Tool"
    description: str = "Performs deep recursive research on a topic by generating multiple search queries and analyzing content from multiple sources."
    args_schema: Type[BaseModel] = DeepResearchToolSchema

    search_tool: SearxNGSearchTool = Field(default_factory=SearxNGSearchTool)
    crawl_tool: CrawlWebsiteTool = Field(default_factory=CrawlWebsiteTool)
    llm: Any = None
    token_counter_callback: Any = None

    def __init__(self, **data):
        super().__init__(**data)
        model_name = data.get('llm_model', settings.GENERAL_MODEL)
        self.llm, self.token_counter_callback = utils_get_llm(model_name, temperature=0.7)

    def _clean_llm_response(self, response: str) -> str:
        """Clean LLM response by removing markdown formatting."""
        # Remove markdown code block markers
        response = response.replace("```json", "").replace("```", "")
        # Strip whitespace
        response = response.strip()
        #logger.debug(f"Cleaned response: {response[:200]}...")
        return response

    def _generate_serp_queries(self, query: str, num_queries: int, learnings: List[str] = None) -> List[Dict]:
        """Generate search queries based on the input query and previous learnings."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert researcher. Generate specific search queries to research the given topic.
            Each query should focus on a unique aspect of the topic. Make queries specific and targeted.

            IMPORTANT: Your response must be a valid JSON array of objects with this exact structure:
            [
                {{
                    "query": "specific search query here",
                    "research_goal": "what we want to learn from this query"
                }}
            ]

            Do not wrap the JSON in markdown code blocks or add any other formatting."""),
            ("human", """Generate {num_queries} unique search queries for researching: {query}

            {previous_learnings}

            Return ONLY a JSON array of objects with 'query' and 'research_goal' fields.
            Do not include any other text, explanation, or markdown formatting.""")
        ])

        previous_learnings = ""
        if learnings:
            previous_learnings = f"Previous learnings to build upon:\n" + "\n".join(f"- {learning}" for learning in learnings)

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = chain.invoke({
                'query': query,
                'num_queries': num_queries,
                'previous_learnings': previous_learnings
            })

            # Clean the response
            cleaned_result = self._clean_llm_response(result)

            # Try to parse JSON response
            try:
                parsed_result = json.loads(cleaned_result)
                # Validate the structure
                if not isinstance(parsed_result, list):
                    raise ValueError("Result must be a JSON array")
                for item in parsed_result:
                    if not isinstance(item, dict) or 'query' not in item or 'research_goal' not in item:
                        raise ValueError("Each item must have 'query' and 'research_goal' fields")
                return parsed_result
            except json.JSONDecodeError as je:
                logger.error(f"JSON parsing error: {str(je)}\nCleaned response was: {cleaned_result[:200]}...")
                raise

        except Exception as e:
            logger.error(f"Error generating SERP queries: {str(e)}")
            # Enhanced fallback with multiple queries
            return [
                {'query': query, 'research_goal': 'Understand the topic broadly'},
                {'query': f"latest developments in {query}", 'research_goal': 'Find recent information'},
                {'query': f"detailed analysis of {query}", 'research_goal': 'Get in-depth understanding'}
            ]

    def _process_content(self, query: str, content: str, num_learnings: int = 3) -> Dict:
        """Process content to extract learnings and follow-up questions."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert researcher analyzing content to extract key learnings and identify follow-up research directions.
            Be specific and information-dense in your learnings. Include entities, metrics, and dates when available.

            IMPORTANT: Your response must be a valid JSON object with this exact structure:
            {{
                "learnings": [
                    "first key learning here",
                    "second key learning here"
                ],
                "follow_up_questions": [
                    "first follow-up question here",
                    "second follow-up question here"
                ]
            }}

            Do not wrap the JSON in markdown code blocks or add any other formatting."""),
            ("human", """For the research query: {query}

            Analyze this content and extract:
            1. Key relevant learnings that will help us answer the research query (maximum {num_learnings}).  Do not generate learnings that are not relevant to the original research query.
            2. Follow-up questions for deeper research

            Content:
            {content}

            Return ONLY a JSON object with 'learnings' and 'follow_up_questions' arrays.
            Do not include any other text, explanation, or markdown formatting.""")
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = chain.invoke({
                'query': query,
                'content': content,
                'num_learnings': num_learnings
            })

            # Clean the response
            cleaned_result = self._clean_llm_response(result)

            # Try to parse JSON response
            try:
                parsed_result = json.loads(cleaned_result)
                # Validate the structure
                if not isinstance(parsed_result, dict):
                    raise ValueError("Result must be a JSON object")
                if 'learnings' not in parsed_result or 'follow_up_questions' not in parsed_result:
                    raise ValueError("Result must have 'learnings' and 'follow_up_questions' fields")
                if not isinstance(parsed_result['learnings'], list) or not isinstance(parsed_result['follow_up_questions'], list):
                    raise ValueError("'learnings' and 'follow_up_questions' must be arrays")
                return parsed_result
            except json.JSONDecodeError as je:
                logger.error(f"JSON parsing error in _process_content: {str(je)}\nCleaned response was: {cleaned_result[:200]}...")
                raise

        except Exception as e:
            logger.error(f"Error processing content: {str(e)}")
            # Enhanced fallback that preserves context
            return {
                'learnings': [
                    f"Unable to extract specific learnings from content about: {query}",
                    "Content processing encountered technical difficulties"
                ],
                'follow_up_questions': [
                    f"What are the key aspects of {query}?",
                    "What are the most recent developments in this area?"
                ]
            }

    def _extract_urls(self, search_results: str) -> List[str]:
        """Extract URLs from search results."""
        urls = []
        for line in search_results.split('\n'):
            if line.startswith('Link: '):
                urls.append(line.replace('Link: ', '').strip())
        #return the first 5 urls
        return urls[:7]

    def _deep_research(self, query: str, breadth: int, depth: int, user_id: int, learnings: List[str] = None, visited_urls: set = None) -> Dict:
        """Recursive function to perform deep research."""
        if learnings is None:
            learnings = []
        if visited_urls is None:
            visited_urls = set()

        # Send initial timing update for this depth level
        if hasattr(self, 'progress_tracker'):
            current_time = datetime.now()
            self.progress_tracker.send_update("timing_update", {
                "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "depth_level": depth,
                "message": f"Starting research at depth {depth}"
            })

        urls_per_query = 5
        expected_urls = breadth * urls_per_query
        total_operations = expected_urls
        current_operation = 0

        # Check for cancellation before starting
        if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
            raise Ignore()

        serp_queries = self._generate_serp_queries(query, breadth, learnings)
        logger.debug(f"SERP queries: {serp_queries}")
        all_learnings = learnings.copy()
        all_urls = visited_urls.copy()

        for query_index, serp_query in enumerate(serp_queries, 1):
            # Send timing update for each query
            if hasattr(self, 'progress_tracker'):
                current_time = datetime.now()
                self.progress_tracker.send_update("timing_update", {
                    "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "depth_level": depth,
                    "query_index": query_index,
                    "message": f"Processing query {query_index}/{len(serp_queries)} at depth {depth}"
                })

            if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
                raise Ignore()

            try:
                search_results = self.search_tool._run(search_query=serp_query['query'])
                urls = self._extract_urls(search_results)
                #logger.debug(f"Search results: {search_results[:100]}")

                new_urls = [url for url in urls if url not in all_urls]
                if not new_urls:
                    continue
                
                try:
                    crawl_result = self.crawl_tool._run(
                        website_url=new_urls,
                        user_id=user_id,
                        max_pages=len(new_urls),
                        max_depth=0,
                        output_type="markdown"
                    )

                    result_data = json.loads(crawl_result)
                    if result_data.get("status") != "success":
                        logger.warning(f"Failed to crawl URLs: {result_data.get('message')}")
                        continue

                    for result in result_data.get("results", []):
                        url = result.get("url")
                        content = result.get("content")

                        if not content or len(content) < 100:
                            logger.warning(f"Insufficient content found for {url}")
                            continue

                        if len(content) > 400000:
                            logger.warning(f"Content too large ({len(content)} chars) for {url}, skipping")
                            continue

                        all_urls.add(url)

                        processed_result = self._process_content(serp_query['query'], content)
                        all_learnings.extend(processed_result['learnings'])

                        current_operation += 1
                        progress_percent = (current_operation / total_operations) * 100

                        if hasattr(self, 'progress_tracker'):
                            self.progress_tracker.send_update("progress", {
                                "message": f"Processing URL {current_operation}/{total_operations} (Query {query_index}/{breadth}, Depth {depth})",
                                "current_depth": depth,
                                "total_depth": depth,
                                "progress_percent": progress_percent
                            })

                    if depth > 1 and processed_result.get('follow_up_questions'):
                        next_query = f"""
                        Previous research goal: {serp_query['research_goal']}
                        Follow-up questions:
                        {chr(10).join(f'- {q}' for q in processed_result['follow_up_questions'])}
                        """.strip()

                        deeper_results = self._deep_research(
                            query=next_query,
                            breadth=max(2, breadth // 2),
                            depth=depth - 1,
                            user_id=user_id,
                            learnings=all_learnings,
                            visited_urls=all_urls
                                )

                        all_learnings = list(set(all_learnings + deeper_results['learnings']))
                        all_urls.update(deeper_results['visited_urls'])
                except Exception as e:
                    logger.error(f"Error processing URLs batch: {str(e)}")
                    continue

            except Exception as e:
                logger.error(f"Error processing query {serp_query['query']}: {str(e)}")
                continue
            
        return {
            'learnings': list(set(all_learnings)),
            'visited_urls': list(all_urls)
            }

    def _write_final_report(self, query: str, learnings: List[str], visited_urls: List[str], start_time: datetime, end_time: datetime, breadth: int, depth: int) -> str:
        duration_minutes = (end_time - start_time).total_seconds() / 60.0
        
        metadata_section = f"""
## Research Metadata

- **Query:** {query}
- **Parameters:**
  - Breadth: {breadth}
  - Depth: {depth}
- **Timing Information:**
  - Start Time: {start_time.strftime("%Y-%m-%d %H:%M:%S")}
  - End Time: {end_time.strftime("%Y-%m-%d %H:%M:%S")}
  - Duration: {round(duration_minutes, 2)} minutes
- **Statistics:**
  - Sources Analyzed: {len(visited_urls)}
  - Key Learnings: {len(learnings)}
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert researcher writing a comprehensive report.
            Create a detailed, well-structured report that synthesizes all learnings.
            Use markdown formatting. Aim for completeness and clarity."""),
            ("human", """Write a detailed report answering this research query: {query}

            Use these research findings:
            {learnings}

            Format as markdown with clear sections. Include all key findings.""")
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            report = chain.invoke({
                'query': query,
                'learnings': "\n".join(f"- {learning}" for learning in learnings)
            })

            sources_section = "\n\n## Sources\n\n" + "\n".join(f"- {url}" for url in visited_urls)
            return metadata_section + "\n" + report + sources_section

        except Exception as e:
            logger.error(f"Error writing final report: {str(e)}")
            return "Error generating report"

    def _run(
        self,
        **kwargs: Any
    ) -> Any:
        try:
            start_time = datetime.now()
            params = self.args_schema(**kwargs)
            logger.info(f"Running deep research tool with params: {params}")

            # Send initial timing update
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("timing_update", {
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": "Starting deep research process"
                })

            results = self._deep_research(
                query=params.query,
                breadth=params.breadth,
                depth=params.depth,
                user_id=params.user_id
            )

            end_time = datetime.now()
            
            report = self._write_final_report(
                query=params.query,
                learnings=results['learnings'],
                visited_urls=results['visited_urls'],
                start_time=start_time,
                end_time=end_time,
                breadth=params.breadth,
                depth=params.depth
            )

            duration_minutes = (end_time - start_time).total_seconds() / 60.0

            # Format times for display
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            # Send final timing information
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("timing_info", {
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "duration_minutes": round(duration_minutes, 2),
                    "breadth": params.breadth,
                    "depth": params.depth,
                    "query": params.query,
                    "message": "Research process completed"
                })

            return {
                'success': True,
                'deep_research_data': {
                    "query": params.query,
                    'report': report,
                    "num_sources": len(results['visited_urls']),
                    "num_learnings": len(results['learnings']),
                    "sources": results['visited_urls'],
                    "learnings": results['learnings'],
                    "timing": {
                        "start_time": start_time_str,
                        "end_time": end_time_str,
                        "duration_minutes": round(duration_minutes, 2)
                    },
                    "parameters": {
                        "breadth": params.breadth,
                        "depth": params.depth
                    }
                }
            }

        except Ignore:
            raise

        except Exception as e:
            end_time = datetime.now()
            duration_minutes = (end_time - start_time).total_seconds() / 60.0
            logger.debug(f"Duration: {duration_minutes}")
            # Send timing information even in case of error
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("timing_info", {
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_minutes": round(duration_minutes, 2)
                })
                
            logger.error(f"Deep Research tool error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'deep_research_data': {
                    "timing": {
                        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "duration_minutes": round(duration_minutes, 2)
                    }
                }
            }
