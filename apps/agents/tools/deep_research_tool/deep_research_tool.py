import os
from typing import Any, Type, List, Dict, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from apps.agents.tools.searxng_tool.searxng_tool import SearxNGSearchTool
from apps.agents.tools.scrapper_tool.scrapper_tool import ScrapperTool
from apps.agents.tools.compression_tool.compression_tool import CompressionTool
from apps.common.utils import get_llm as utils_get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from django.conf import settings
import json
import logging
from celery.exceptions import Ignore
from datetime import datetime
from apps.research.models import Research  # Import here to avoid circular imports

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
# *   **Direct Answers:** Is a simple, direct answer possible (lower depth), or will deeper investigation be required (higher depth)?

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

    model_config = {
        "use_enum_values": True,
        "extra": "forbid",
        "json_schema_extra": {
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
    }

    query: str = Field(
        ...,
        description="The query to research deeply.",
        examples=["What are the latest developments in quantum computing?"]
    )
    breadth: int = Field(
        ...,
        description="Number of parallel search queries to make (recommended 2-10)",
        ge=1,
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
    scrapper_tool: ScrapperTool = Field(default_factory=ScrapperTool)
    compression_tool: CompressionTool = Field(default_factory=CompressionTool)
    llm: Any = None
    token_counter_callback: Any = None
    # Define token tracking fields as proper Pydantic fields with default values
    total_input_tokens: int = Field(0, description="Total input tokens used")
    total_output_tokens: int = Field(0, description="Total output tokens used")

    def __init__(self, **data):
        super().__init__(**data)
        model_name = data.get('llm_model', settings.GENERAL_MODEL)
        self.llm, self.token_counter_callback = utils_get_llm(model_name, temperature=0.7)
        # Token tracking is now handled by the Pydantic fields above, so no need to initialize here

    def _update_token_counters(self):
        """Update total token counts from the token counter callback"""
        if hasattr(self, 'token_counter_callback') and self.token_counter_callback:
            current_input = getattr(self.token_counter_callback, 'input_tokens', 0)
            current_output = getattr(self.token_counter_callback, 'output_tokens', 0)
            
            # Calculate incremental usage since last check
            input_diff = current_input - self.total_input_tokens
            output_diff = current_output - self.total_output_tokens
            
            if input_diff > 0 or output_diff > 0:
                logger.debug(f"Token usage - Input: +{input_diff}, Output: +{output_diff}")
                
            # Update totals
            self.total_input_tokens = current_input
            self.total_output_tokens = current_output
        
        return self.total_input_tokens, self.total_output_tokens

    def send_update(self, update_type: str, data: Dict):
        """Send update through progress tracker."""
        if hasattr(self, 'progress_tracker'):
            # Send update through progress tracker
            self.progress_tracker.send_update(update_type, data)
            logger.debug(f"Sent {update_type} update: {data.get('title', 'No title')}")

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
                "explanation": "Analyzing query to determine optimal search approach",
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
            
            # Update token counters after LLM call
            self._update_token_counters()

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

    def _extract_compression_tool_tokens(self, compression_result: str) -> tuple:
        """Extract token usage information from CompressionTool result."""
        try:
            result_data = json.loads(compression_result)
            input_tokens = result_data.get("llm_input_tokens", 0)
            output_tokens = result_data.get("llm_output_tokens", 0)
            logger.debug(f"Extracted token usage from CompressionTool - Input: {input_tokens}, Output: {output_tokens}")
            return input_tokens, output_tokens
        except Exception as e:
            logger.error(f"Error extracting token usage from CompressionTool: {str(e)}")
            return 0, 0
            
    def _extract_searxng_tool_tokens(self, search_results: str) -> tuple:
        """Extract token usage information from SearxNGTool result."""
        try:
            # Search for token usage information in the search results
            token_info_marker = "Relevance filtering token usage - Input:"
            if token_info_marker in search_results:
                # Extract the token usage line
                lines = search_results.split('\n')
                for line in lines:
                    if token_info_marker in line:
                        # Parse the token information
                        # Format: "Relevance filtering token usage - Input: X, Output: Y, Total: Z"
                        parts = line.split(',')
                        input_tokens = int(parts[0].split(':')[-1].strip())
                        output_tokens = int(parts[1].split(':')[-1].strip())
                        logger.debug(f"Extracted token usage from SearxNGTool - Input: {input_tokens}, Output: {output_tokens}")
                        return input_tokens, output_tokens
            return 0, 0
        except Exception as e:
            logger.error(f"Error extracting token usage from SearxNGTool: {str(e)}")
            return 0, 0
            
    def _update_token_counters_from_subtool(self, input_tokens: int, output_tokens: int):
        """Update token counters with usage from a sub-tool."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        logger.debug(f"Added sub-tool token usage - Input: +{input_tokens}, Output: +{output_tokens}")
        logger.debug(f"Updated cumulative totals - Input: {self.total_input_tokens}, Output: {self.total_output_tokens}")

    def _process_content(self, query: str, content: str, num_learnings: int = 3, guidance: Optional[str] = None) -> Dict:
        """Process content to extract learnings and follow-up questions using the CompressionTool."""
        # Log content size and type information
        logger.info(f"_process_content called with query: {query[:50]}...")
        logger.info(f"Content type: {type(content)}, length: {len(content) if isinstance(content, str) else 'not string'}")
        
        # Use CompressionTool to extract key learnings with 'focused' detail level
        try:
            # Run the compression tool with focused detail
            compression_result = self.compression_tool._run(
                content=content,
                max_tokens=8192,  # Use a reasonable token limit
                detail_level="focused"  # Use focused setting as requested
            )
            
            # Extract and add token usage from CompressionTool
            input_tokens, output_tokens = self._extract_compression_tool_tokens(compression_result)
            self._update_token_counters_from_subtool(input_tokens, output_tokens)
            
            # Parse the JSON result
            parsed_compression = json.loads(compression_result)
            
            if "error" in parsed_compression:
                logger.error(f"CompressionTool error: {parsed_compression['error']}")
                raise ValueError(f"CompressionTool error: {parsed_compression.get('message', 'Unknown error')}")
                
            # Get the processed content
            processed_content = parsed_compression.get("processed_content", "")
            
            if not processed_content:
                logger.error("No processed content returned from CompressionTool")
                raise ValueError("No processed content returned from CompressionTool")
            
            logger.info(f"Successfully processed content with CompressionTool, length: {len(processed_content)}")
            
            # Now we need to generate follow-up questions using LLM
            follow_up_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert researcher. Based on the provided notes, suggest follow-up questions
                for deeper research. Focus on gaps in knowledge, unexplored areas, and potential new directions.
                
                IMPORTANT: Your response must be a valid JSON array of strings containing only the follow-up questions.
                Do not wrap the JSON in markdown code blocks or add any other formatting."""),
                ("human", """For the research query: {query}
                
                Based on these notes:
                {processed_content}
                
                Use this guidance to generate follow-up questions:
                {guidance}
                
                Generate {num_questions} follow-up questions for deeper research.
                
                Return ONLY a JSON array of strings.
                Do not include any other text, explanation, or markdown formatting.""")
            ])
            
            follow_up_chain = follow_up_prompt | self.llm | StrOutputParser()
            
            follow_up_result = follow_up_chain.invoke({
                'query': query,
                'processed_content': processed_content,
                'guidance': guidance or "",
                'num_questions': 3  # Generate 3 follow-up questions
            })
            
            # Update token counters after LLM call
            self._update_token_counters()
            
            # Clean and parse the follow-up questions
            cleaned_follow_up = self._clean_llm_response(follow_up_result)
            follow_up_questions = json.loads(cleaned_follow_up)
            
            # Use the entire processed content as the learning
            # The CompressionTool with 'focused' setting already gives us what we need
            learnings = [processed_content]
            
            # Log extracted learnings
            logger.info(f"Successfully extracted learning from content using CompressionTool")
            logger.info(f"Learning: {processed_content[:100]}...")
            
            return {
                'learnings': learnings,
                'follow_up_questions': follow_up_questions if isinstance(follow_up_questions, list) else []
            }

        except Exception as e:
            logger.error(f"Error processing content with CompressionTool: {str(e)}", exc_info=True)
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
                "title": f" {depth}",
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
        
        # Log initial state
        logger.info(f"_deep_research initial state: local learnings={len(learnings)}, all_learnings={len(all_learnings)}")

        for query_index, serp_query in enumerate(serp_queries, 1):
            if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
                raise Ignore()

            try:
                # Use the new relevant_results_only parameter
                search_results = self.search_tool._run(
                    search_query=serp_query['query'],
                    relevant_results_only=True  # Filter for relevant results only
                )
                
                # Extract and add token usage from SearxNGTool
                input_tokens, output_tokens = self._extract_searxng_tool_tokens(search_results)
                self._update_token_counters_from_subtool(input_tokens, output_tokens)
                
                urls = self._extract_urls(search_results)
                #logger.debug(f"Search results: {search_results[:100]}")

                new_urls = [url for url in urls if url not in all_urls]
                if not new_urls:
                    continue
                
                for url in new_urls:
                    try:
                        # Use ScrapperTool instead of CrawlWebsiteTool
                        scrape_result = self.scrapper_tool._run(
                            url=url,
                            user_id=user_id,
                            output_type="text",
                            cache=True,
                            stealth=True
                        )

                        result_data = json.loads(scrape_result)
                        if not result_data.get("success", False):
                            logger.warning(f"Failed to scrape URL: {url} - {result_data.get('error')}")
                            continue

                        content = result_data.get("text", "")

                        if not content or len(content) < 100:
                            logger.warning(f"Insufficient content found for {url}")
                            continue

                        if len(content) > 400000:
                            logger.warning(f"Content too large ({len(content)} chars) for {url}, skipping")
                            continue

                        all_urls.add(url)

                        try:
                            # Notify about analyzing this source
                            if hasattr(self, 'progress_tracker'):
                                self.progress_tracker.send_update("reasoning", {
                                    "step": "content_analysis",
                                    "title": "Analyzing Source Content",
                                    "explanation": f"Phase {depth}\n{url}",
                                    "details": {
                                        "url": url,
                                        "depth": depth
                                    }
                                })

                            content_length = len(content)
                            logger.info(f"Processing {content_length/1024:.1f} KB from {url}")

                            if hasattr(self, 'progress_tracker'):
                                self.progress_tracker.send_update("reasoning", {
                                    "step": "content_analysis",
                                    "title": "Analyzing Source Content",
                                    "explanation": f"Phase {depth}\n{url}",
                                    "details": {
                                        "url": url,
                                        "source_length": content_length,
                                        "depth": depth
                                    }
                                })

                            # Store current URL for subclasses to access
                            self._current_url = url
                            
                            # Process the content
                            result = self._process_content(query, content, guidance=guidance)
                            
                            # Clear current URL after processing
                            self._current_url = None
                            
                            new_learnings = result.get('learnings', [])

                            if not new_learnings or new_learnings[0].startswith("Unable to extract"):
                                logger.error(f"Failed to extract learnings from {url}")
                                continue

                            # Log learnings being added
                            logger.info(f"Adding {len(new_learnings)} new learnings from {url}")
                            logger.debug(f"First learning sample: {new_learnings[0][:100]}...")
                            
                            learnings.extend(new_learnings)
                            # Add new learnings to all_learnings as well
                            all_learnings.extend(new_learnings)
                            logger.info(f"After adding: local learnings={len(learnings)}, all_learnings={len(all_learnings)}")

                            # Handle follow-up questions for deeper research
                            if depth > 1 and result.get('follow_up_questions'):
                                next_query = f"""
                                Previous research goal: {serp_query['research_goal']}
                                Follow-up questions:
                                {chr(10).join(f'- {q}' for q in result['follow_up_questions'])}
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
                                
                                # Log after recursive call
                                logger.info(f"After recursive call: local learnings={len(learnings)}, all_learnings={len(all_learnings)}")

                        except Exception as e:
                            logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
                            continue

                    except Exception as e:
                        logger.error(f"Error scraping URL {url}: {str(e)}")
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

        # Log the state of learnings before return
        logger.info(f"Depth {depth} complete - Collected {len(all_learnings)} total learnings")
        if all_learnings:
            logger.debug(f"Sample learnings: {all_learnings[0][:100]}...")
            
        # Before deduplication
        logger.info(f"Before deduplication: {len(all_learnings)} learnings")
        if len(all_learnings) == 0:
            logger.error("No learnings collected - check processing or content extraction!")
        
        deduplicated_learnings = list(set(all_learnings))  # Deduplicate learnings
        logger.info(f"After deduplication: {len(deduplicated_learnings)} learnings")
        
        # Check if any learnings were lost during deduplication
        if len(deduplicated_learnings) < len(all_learnings):
            logger.warning(f"Lost {len(all_learnings) - len(deduplicated_learnings)} learnings during deduplication")

        return {
            'learnings': deduplicated_learnings,  # Using the tracked deduplicated list
            'visited_urls': list(all_urls)
            }

    def _write_final_report(self, query: str, guidance: str, learnings: List[str], visited_urls: List[str], start_time: datetime, end_time: datetime, breadth: int, depth: int) -> str:
        # Log the incoming data
        logger.info(f"_write_final_report received {len(learnings) if learnings else 0} learnings and {len(visited_urls) if visited_urls else 0} URLs")
        
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("reasoning", {
                "step": "report_generation",
                "title": "Generating Final Report",
                "explanation": "Synthesizing research findings into a comprehensive report",
                "details": {
                    "total_learnings": len(learnings) if learnings else 0,
                    "total_sources": len(visited_urls) if visited_urls else 0,
                    "research_duration": f"{(end_time - start_time).total_seconds() / 60.0:.2f} minutes"
                }
            })

        duration_minutes = (end_time - start_time).total_seconds() / 60.0
        
        # Check if we have any learnings
        if not learnings or len(learnings) == 0:
            logger.error("No learnings found for report generation")
            return "Error: No research findings were collected. The research process did not yield any usable results. This could be due to:\n\n" \
                   "1. Limited information available on the topic\n" \
                   "2. Issues with content extraction from web pages\n" \
                   "3. The search terms may need to be refined\n\n" \
                   "Please try again with different parameters or a different query."
        
        # Log the learnings for debugging
        logger.info(f"Generating report with {len(learnings)} learnings")
        for i, learning in enumerate(learnings[:5]):  # Log first 5 learnings for debugging
            logger.info(f"Learning {i+1}: {learning[:100]}...")
        
        # Get current token usage before generating the report
        input_tokens, output_tokens = self._update_token_counters()
        
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
- **Token Usage (Comprehensive):**
  - Input Tokens: {input_tokens:,}
  - Output Tokens: {output_tokens:,}
  - Total Tokens: {input_tokens + output_tokens:,}
  - Note: Includes all LLM calls, sub-tools, and filtering operations
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert analyst synthesizing research findings into comprehensive reports that are easy to understand with structure appropriate for the query and guidance.
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

Provide a response that is easy to understand with structure appropriate for the query and guidance.  Develop bespoke sections for the report based on the query and guidance.  If asked a question, summarize key findings and recommendations, analyze critical factors, evaluate practical aspects, and examine relevant implications and outcomes.
Otherwise provide a resposne that is resposive to the query and guidance (i.e. if guidance says write a long form article, then write a long form article, if guidance says find a list of things, then provide a list).

Conclude with actionable insights based on the analysis.  Above all make sure you follow the instructions given in the guidance.""")
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            report = chain.invoke({
                'query': query,
                'learnings': "\n".join(f"- {learning}" for learning in learnings),
                'guidance': guidance or "",
                'current_date': datetime.now().strftime("%Y-%m-%d")
            })
            
            # Update token counters after generating report
            final_input_tokens, final_output_tokens = self._update_token_counters()
            
            # Get tokens used specifically for report generation
            report_input_tokens = final_input_tokens - input_tokens
            report_output_tokens = final_output_tokens - output_tokens
            
            logger.info(f"Report generation token usage - Input: {report_input_tokens}, Output: {report_output_tokens}")
            
            # Update metadata section with final token counts
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
- **Token Usage (Comprehensive):**
  - Input Tokens: {final_input_tokens:,}
  - Output Tokens: {final_output_tokens:,}
  - Total Tokens: {final_input_tokens + final_output_tokens:,}
  - Report Generation: {report_input_tokens + report_output_tokens:,} tokens
  - Note: Includes all LLM calls, sub-tools, and filtering operations
"""

            # Log the generated report for debugging
            logger.info(f"Generated report length: {len(report)}")
            logger.debug(f"Report preview: {report[:500]}...")

            sources_section = "\n\n## Sources\n\n" + "\n".join(f"- {url}" for url in visited_urls)
            final_report = report + sources_section + "\n\n" + metadata_section

            # Check if the report contains fabrication disclaimer
            fabrication_indicators = [
                "unfortunately, are missing from the prompt",
                "I will proceed by making reasonable assumptions",
                "I will fabricate plausible research",
                "no research findings were provided",
                "missing from the input"
            ]
            
            for indicator in fabrication_indicators:
                if indicator.lower() in report.lower():
                    logger.error(f"Report contains fabrication indicator: {indicator}")
                    return "Error: The report generation system detected that it was attempting to fabricate research findings. This indicates an issue with the research process. Please try again with different parameters or a different query."

            # After generating the report
            if hasattr(self, 'progress_tracker'):
                self.progress_tracker.send_update("reasoning", {
                    "step": "complete",
                    "title": "Research Complete",
                    "explanation": "Research process has finished",
                    "details": {
                        "total_time": f"{(end_time - start_time).total_seconds() / 60.0:.2f} minutes",
                        "total_sources": len(visited_urls),
                        "total_learnings": len(learnings),
                        "total_tokens": final_input_tokens + final_output_tokens
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
            
            # Reset token counters at the start of each run
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            if hasattr(self, 'token_counter_callback') and self.token_counter_callback:
                self.token_counter_callback.input_tokens = 0
                self.token_counter_callback.output_tokens = 0

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
            
            # Log the results received from _deep_research
            logger.info(f"_run received results from _deep_research with {len(results.get('learnings', []))} learnings")
            if 'learnings' in results and results['learnings']:
                logger.debug(f"First learning received: {results['learnings'][0][:100]}...")
            else:
                logger.error("No learnings were returned from _deep_research!")

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
            
            # Get final token counts
            final_input_tokens, final_output_tokens = self._update_token_counters()

            # Send final timing information and report
            if hasattr(self, 'progress_tracker'):
                # First update with the report
                self.progress_tracker.send_update("report", {
                    "report": report
                })
                
                # Then update status to completed
                self.progress_tracker.send_update("status", {
                    "status": "completed",
                    "progress_percent": 100,
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "duration_minutes": round(duration_minutes, 2),
                    "message": "Research process completed",
                    "tokens": {
                        "input": final_input_tokens,
                        "output": final_output_tokens,
                        "total": final_input_tokens + final_output_tokens
                    }
                })

            # Log report structure before returning
            logger.info(f"Returning report of type {type(report).__name__} and length {len(report)}")
            logger.debug(f"Report preview: {report[:200]}...")
            logger.info(f"Total token usage - Input: {final_input_tokens}, Output: {final_output_tokens}, Total: {final_input_tokens + final_output_tokens}")

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
                    },
                    "token_usage": {
                        "input_tokens": final_input_tokens,
                        "output_tokens": final_output_tokens,
                        "total_tokens": final_input_tokens + final_output_tokens,
                        "note": "Includes all LLM calls, sub-tools, and filtering operations"
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
