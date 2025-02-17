import os
from typing import Any, Type, List, Dict, Optional
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
                    "user_id": 1,
                    "guidance": "Focus on practical applications and industry adoption"
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
    guidance: Optional[str] = Field(
        None,
        description="Optional guidance to influence content processing"
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

    def _generate_serp_queries(self, query: str, num_queries: int, learnings: List[str] = None, guidance: Optional[str] = None) -> List[Dict]:
        """Generate search queries based on the input query and previous learnings."""
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "query_planning",
                "title": "Planning Search Strategy",
                "explanation": f"Analyzing query to determine optimal search approach",
                "details": {
                    "query": query,
                    "context": "Previous learnings" if learnings else "Initial research",
                    "num_queries_planned": num_queries
                }
            })

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert researcher on {current_date}. Generate specific search queries to research the given topic.
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
            Use this guidance to generate the search queries: {guidance}
            Previous learnings to build upon:
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
                'guidance': guidance or "",
                'previous_learnings': previous_learnings,
                'current_date': datetime.now().strftime("%Y-%m-%d")
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

                # After generating queries, explain the reasoning
                if hasattr(self, 'progress_tracker'):
                    self.progress_tracker.send_update("reasoning", {
                        "step": "search_queries",
                        "title": "Generated Search Queries",
                        "explanation": "Created targeted queries to explore different aspects",
                        "details": {
                            "queries": [q['query'] for q in parsed_result],
                            "goals": [q['research_goal'] for q in parsed_result],
                            "reasoning": "Each query targets a specific aspect of the research topic to ensure comprehensive coverage"
                        }
                    })

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

    def _process_content(self, query: str, content: str, num_learnings: int = 3, guidance: Optional[str] = None) -> Dict:
        """Process content to extract learnings and follow-up questions."""
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "content_analysis",
                "title": "Analyzing Source Content",
                "explanation": "Evaluating relevance and extracting key information",
                "details": {
                    "source_length": len(content),
                    "focus": query,
                    "analysis_approach": "Identifying key facts, metrics, and insights relevant to the research query"
                }
            })

        guidance_instruction = f"\nAdditional guidance for analysis: {guidance}" if guidance else ""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are an expert researcher analyzing content on {{current_date}} to extract key learnings and identify follow-up research directions.
            Be specific and information-dense in your learnings. Include entities, metrics, and dates when available.{guidance_instruction}

            IMPORTANT: Your response must be a valid JSON object with this exact structure:
            {{{{
                "learnings": [
                    "first key learning here",
                    "second key learning here"
                ],
                "follow_up_questions": [
                    "first follow-up question here",
                    "second follow-up question here"
                ]
            }}}}

            Do not wrap the JSON in markdown code blocks or add any other formatting."""),
            ("human", """For the research query: {query}

            Analyze this content and extract:
            1. Key relevant learnings that will help us answer the research query (maximum {num_learnings}).  Do not generate learnings that are not relevant to the original research query.
            2. Follow-up questions for deeper research

            Use this guidance to analyze the content:
            {guidance}

            Content:
            {content}

            Return ONLY a JSON object with 'learnings' and 'follow_up_questions' arrays.
            Do not include any other text, explanation, or markdown formatting.""")
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = chain.invoke({
                'query': query,
                'guidance': guidance or "",
                'content': content,
                'num_learnings': num_learnings,
                'current_date': datetime.now().strftime("%Y-%m-%d")
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

                # After processing, explain what was found
                if hasattr(self, 'progress_tracker'):
                    self.progress_tracker.send_update("reasoning", {
                        "step": "insights_extracted",
                        "title": "Extracted Key Insights",
                        "explanation": "Identified relevant information and potential follow-up areas",
                        "details": {
                            "num_learnings": len(parsed_result['learnings']),
                            "key_findings": parsed_result['learnings'],
                            "follow_up_areas": parsed_result['follow_up_questions'],
                            "synthesis": "Information has been analyzed and connected to the main research goals"
                        }
                    })

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
        return urls[:5]

    def _deep_research(self, query: str, breadth: int, depth: int, user_id: int, guidance: Optional[str] = None, learnings: List[str] = None, visited_urls: set = None) -> Dict:
        """Recursive function to perform deep research."""
        if learnings is None:
            learnings = []
        if visited_urls is None:
            visited_urls = set()

        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "research_phase",
                "title": f"Research Phase {depth}",
                "explanation": "Starting new research iteration",
                "details": {
                    "depth_level": depth,
                    "breadth": breadth,
                    "context": "Using previous findings to guide deeper research" if learnings else "Initial research phase",
                    "strategy": "Exploring broader topics" if depth == 1 else "Diving deeper into specific areas"
                }
            })

        urls_per_query = 5
        expected_urls = breadth * urls_per_query
        total_operations = expected_urls
        current_operation = 0

        # Check for cancellation before starting
        if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
            raise Ignore()

        serp_queries = self._generate_serp_queries(query, breadth, learnings, guidance)
        logger.debug(f"SERP queries: {serp_queries}")
        all_learnings = learnings.copy()
        all_urls = visited_urls.copy()

        for query_index, serp_query in enumerate(serp_queries, 1):
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("reasoning", {
                    "step": "source_selection",
                    "title": f"Evaluating Sources",
                    "explanation": f"Finding relevant sources for: {serp_query['research_goal']}",
                    "details": {
                        "query": serp_query['query'],
                        "goal": serp_query['research_goal'],
                        "selection_criteria": "Prioritizing authoritative and recent sources"
                    }
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

                        processed_result = self._process_content(
                            query=serp_query['query'],
                            content=content,
                            guidance=guidance
                        )
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
                            guidance=guidance,
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
            
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "depth_complete",
                "title": f"Completed Depth Level {depth}",
                "explanation": "Finished current research iteration",
                "details": {
                    "new_learnings": len(all_learnings) - (len(learnings) if learnings else 0),
                    "new_urls": len(all_urls) - (len(visited_urls) if visited_urls else 0)
                }
            })

        return {
            'learnings': list(set(all_learnings)),
            'visited_urls': list(all_urls)
            }

    def _write_final_report(self, query: str, guidance: str, learnings: List[str], visited_urls: List[str], start_time: datetime, end_time: datetime, breadth: int, depth: int) -> str:
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "report_generation",
                "title": "Generating Final Report",
                "explanation": "Synthesizing research findings into a comprehensive report",
                "details": {
                    "total_learnings": len(learnings),
                    "total_sources": len(visited_urls),
                    "research_duration": f"{(end_time - start_time).total_seconds() / 60.0:.2f} minutes"
                }
            })

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
            ("system", """You are an expert analyst synthesizing research findings into comprehensive reports.
Your analysis should:
- Present information in a clear, logical narrative
- Support claims with evidence from provided research
- Balance depth with accessibility
- Consider practical implications
- Evaluate relevant trade-offs

Format using clean markdown with:
- Clear section hierarchy (### for main sections, #### for subsections)
- Minimal formatting for readability
- Appropriate use of technical notation when needed"""),

("human", """Analyze the following query: {query}

Using these research findings:
{learnings}

Following this guidance:
{guidance}

Provide a comprehensive report that:
1. Summarizes key findings and recommendations
2. Analyzes critical factors and considerations
3. Evaluates practical implementation aspects
4. Examines relevant implications and outcomes

Include supporting evidence and citations [^1] where appropriate.
Conclude with actionable insights based on the analysis.""")
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            report = chain.invoke({
                'query': query,
                'learnings': "\n".join(f"- {learning}" for learning in learnings),
                'guidance': guidance or "",
                'current_date': datetime.now().strftime("%Y-%m-%d")
            })

            sources_section = "\n\n## Sources\n\n" + "\n".join(f"- {url}" for url in visited_urls)
            final_report = metadata_section + "\n" + report + sources_section

            # After generating the report
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("reasoning", {
                    "step": "complete",
                    "title": "Research Complete",
                    "explanation": "Research process has finished",
                    "details": {
                        "total_time": f"{(end_time - start_time).total_seconds() / 60.0:.2f} minutes",
                        "total_sources": len(visited_urls),
                        "total_learnings": len(learnings)
                    }
                })

            return final_report

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
                self.progress_tracker.send_update("timing", {
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": "Starting deep research process"
                })

            results = self._deep_research(
                query=params.query,
                breadth=params.breadth,
                depth=params.depth,
                user_id=params.user_id,
                guidance=params.guidance
            )

            end_time = datetime.now()
            
            report = self._write_final_report(
                query=params.query,
                guidance=params.guidance,
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
                self.progress_tracker.send_update("timing", {
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
                self.progress_tracker.send_update("timing", {
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
