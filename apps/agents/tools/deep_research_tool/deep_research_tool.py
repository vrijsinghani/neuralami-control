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

logger = logging.getLogger(__name__)

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
        self.llm, self.token_counter_callback = utils_get_llm(settings.GENERAL_MODEL, temperature=0.7)

    def _clean_llm_response(self, response: str) -> str:
        """Clean LLM response by removing markdown formatting."""
        # Remove markdown code block markers
        response = response.replace("```json", "").replace("```", "")
        # Strip whitespace
        response = response.strip()
        logger.debug(f"Cleaned response: {response[:200]}...")
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

    def _extract_urls(self, search_results: str) -> List[str]:
        """Extract URLs from search results."""
        urls = []
        for line in search_results.split('\n'):
            if line.startswith('Link: '):
                urls.append(line.replace('Link: ', '').strip())
        return urls[:5]  # Limit to top 5 results

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
            1. Key learnings (maximum {num_learnings})
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

    def _deep_research(self, query: str, breadth: int, depth: int, user_id: int, learnings: List[str] = None, visited_urls: List[str] = None) -> Dict:
        """Recursive function to perform deep research."""
        if learnings is None:
            learnings = []
        if visited_urls is None:
            visited_urls = []
            
        # Check for cancellation before starting
        if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
            raise Ignore()
            
        # Generate search queries
        serp_queries = self._generate_serp_queries(query, breadth, learnings)
        all_learnings = learnings.copy()
        all_urls = visited_urls.copy()
        
        for serp_query in serp_queries:
            # Check for cancellation before each query
            if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
                raise Ignore()
                
            try:
                # Search for content
                search_results = self.search_tool._run(search_query=serp_query['query'])
                urls = self._extract_urls(search_results)
                logger.debug(f"Search results: {search_results[:100]}")
                
                # Process each URL
                for url in urls:
                    # Check for cancellation before processing each URL
                    if hasattr(self, 'progress_tracker') and self.progress_tracker.check_cancelled():
                        raise Ignore()
                        
                    if url in all_urls:
                        continue
                        
                    try:
                        # Use CrawlWebsiteTool with single_page mode
                        crawl_result = self.crawl_tool._run(
                            website_url=url,
                            user_id=user_id,
                            single_page=True,
                            max_pages=1,
                            extraction_config={
                                "type": "basic",
                                "params": {
                                    "word_count_threshold": 100,
                                    "only_text": True
                                }
                            }
                        )
                        
                        # Parse the JSON response
                        result_data = json.loads(crawl_result)
                        if result_data.get("status") != "success":
                            logger.warning(f"Failed to crawl {url}: {result_data.get('message')}")
                            continue
                            
                        content = result_data.get("content", "")
                        if not content or len(content) < 100:
                            continue
                            
                        all_urls.append(url)
                        
                        # Process content
                        result = self._process_content(serp_query['query'], content)
                        all_learnings.extend(result['learnings'])
                        
                        # Recursive research if depth allows
                        if depth > 1 and result['follow_up_questions']:
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
                                learnings=all_learnings,
                                visited_urls=all_urls
                            )
                            
                            all_learnings = list(set(all_learnings + deeper_results['learnings']))
                            all_urls = list(set(all_urls + deeper_results['visited_urls']))
                            
                    except Exception as e:
                        logger.error(f"Error processing URL {url}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error processing query {serp_query['query']}: {str(e)}")
                continue
                
        return {
            'learnings': list(set(all_learnings)),
            'visited_urls': list(set(all_urls))
        }

    def _write_final_report(self, query: str, learnings: List[str], visited_urls: List[str]) -> str:
        """Generate a final report summarizing the research."""
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
            
            # Add sources section
            sources_section = "\n\n## Sources\n\n" + "\n".join(f"- {url}" for url in visited_urls)
            return report + sources_section
            
        except Exception as e:
            logger.error(f"Error writing final report: {str(e)}")
            return "Error generating report"

    def _run(
        self,
        **kwargs: Any
    ) -> Any:
        """Execute the deep research tool pipeline."""
        try:
            # Validate parameters using schema
            params = self.args_schema(**kwargs)
            logger.info(f"Running deep research tool with params: {params}")
            
            # Perform deep research
            results = self._deep_research(
                query=params.query,
                breadth=params.breadth,
                depth=params.depth,
                user_id=params.user_id
            )
            
            # Generate final report
            report = self._write_final_report(
                query=params.query,
                learnings=results['learnings'],
                visited_urls=results['visited_urls']
            )
            
            # Return structured results
            return {
                'success': True,
                'deep_research_data': {
                    "query": params.query,
                    'report': report,
                    "num_sources": len(results['visited_urls']),
                    "num_learnings": len(results['learnings']),
                    "sources": results['visited_urls'],
                    "learnings": results['learnings']
                }
            }
            
        except Ignore:
            # Re-raise Ignore exception to be handled by Celery
            raise
            
        except Exception as e:
            logger.error(f"Deep Research tool error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'deep_research_data': {}
            } 