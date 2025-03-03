import os
import requests
import json
from typing import Any, Type, Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict
from crewai.tools import BaseTool
from apps.common.utils import get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    """Model for validating search result relevance responses."""
    is_relevant: bool = Field(..., description="Whether the result is relevant to the search query")
    reason: str = Field(..., description="Reason why the result is or is not relevant")

class RelevanceResponse(BaseModel):
    """Model for validating the full LLM response for relevance filtering."""
    results: List[SearchResult] = Field(..., description="List of search results with relevance determinations")

class SearxNGToolSchema(BaseModel):
    """Input schema for SearxNGSearchTool."""
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    search_query: str = Field(description="The search query to be used.")
    relevant_results_only: bool = Field(
        default=False, 
        description="If True, will filter results to only those directly relevant to the search query using LLM."
    )

class SearxNGSearchTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Search the internet"
    description: str = "Searches the internet displaying titles, links, snippets, engines, and categories."
    args_schema: Type[BaseModel] = SearxNGToolSchema
    search_url: str = "https://search.neuralami.com"
    n_results: Optional[int] = None
    llm: Any = None
    token_counter_callback: Any = None

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize LLM for relevance filtering
        model_name = data.get('llm_model', settings.SUMMARIZER)  # Use summarizer model which is optimized for content evaluation
        self.llm, self.token_counter_callback = get_llm(model_name, temperature=0.1)  # Low temperature for consistent evaluations

    def _filter_relevant_results(self, search_query: str, results: List[Dict]) -> List[Dict]:
        """Filter search results to keep only those relevant to the query."""
        if not results:
            return []
        
        # Extract snippets and other info for LLM evaluation
        snippets_with_metadata = []
        for i, result in enumerate(results):
            snippet = {
                'id': i,
                'title': result.get('title', 'No Title'),
                'snippet': result.get('content', 'No Snippet'),
                'url': result.get('url', 'No URL')
            }
            snippets_with_metadata.append(snippet)
        
        # Create prompt for LLM to evaluate relevance
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at evaluating search result relevance.
            For each search result, determine if it is directly relevant to the search query.
            
            A result is relevant if:
            1. It directly addresses the specific topic or question in the search query
            2. It provides useful information related to the core intent of the query
            3. It comes from a credible source for the topic
            
            A result is NOT relevant if:
            1. It's only tangentially related to the query
            2. It focuses primarily on a different topic
            3. It appears to be spam, misleading, or low-quality content
            
            Provide your evaluation as a JSON array where each item has:
            - "is_relevant": boolean (true/false)
            - "reason": brief explanation of your decision
            
            Your response must be VALID JSON with this structure:
            {{
              "results": [
                {{"is_relevant": true, "reason": "explanation"}},
                {{"is_relevant": false, "reason": "explanation"}}
              ]
            }}
            """),
            ("human", """Search Query: {search_query}
            
            Search Results:
            {results}
            
            Evaluate each result's relevance to the search query.
            Return ONLY a JSON object with the structure specified.
            Do not include any other text, explanation, or markdown formatting.""")
        ])
        
        chain = prompt | self.llm | StrOutputParser()
        
        max_retries = 3
        retries = 0
        
        while retries < max_retries:
            try:
                # Format results for the prompt
                formatted_results = json.dumps(snippets_with_metadata, indent=2)
                
                # Get LLM evaluation
                logger.info(f"Evaluating relevance of {len(results)} search results for query: {search_query}")
                llm_response = chain.invoke({
                    'search_query': search_query,
                    'results': formatted_results
                })
                
                # Clean and parse response
                llm_response = llm_response.strip()
                if llm_response.startswith("```json"):
                    llm_response = llm_response.replace("```json", "", 1)
                if llm_response.endswith("```"):
                    llm_response = llm_response.rstrip("```")
                llm_response = llm_response.strip()
                
                logger.debug(f"LLM relevance response (first 200 chars): {llm_response[:200]}...")
                
                try:
                    # Parse and validate with Pydantic
                    parsed_response = json.loads(llm_response)
                    
                    # Check for expected structure before validation
                    if not isinstance(parsed_response, dict) or "results" not in parsed_response:
                        logger.warning("LLM response missing 'results' key or not a dict. Response: " + llm_response[:500])
                        raise ValueError("Response missing 'results' key")
                    
                    relevance_data = RelevanceResponse(**parsed_response)
                    
                    # Instead of retrying when we don't have evaluations for all results,
                    # just work with what we have and log which items weren't evaluated
                    if len(relevance_data.results) != len(results):
                        logger.info(f"LLM returned {len(relevance_data.results)} evaluations for {len(results)} results. Working with partial results.")
                        unevaluated_indices = set(range(len(results))) - set(i for i in range(min(len(relevance_data.results), len(results))))
                        if unevaluated_indices:
                            logger.debug(f"Results at indices {unevaluated_indices} were not evaluated by the LLM.")
                    
                    # Filter results based on relevance - only include explicitly relevant results
                    relevant_results = []
                    excluded_results = []
                    
                    for i, result in enumerate(results):
                        # Only include result if it was evaluated and marked as relevant
                        if i < len(relevance_data.results) and relevance_data.results[i].is_relevant:
                            relevant_results.append(result)
                        else:
                            excluded_results.append(result)
                    
                    # Log excluded URLs
                    if excluded_results:
                        excluded_urls = [r.get('url', 'No URL') for r in excluded_results]
                        excluded_reasons = []
                        
                        for i, result in enumerate(results):
                            if i < len(relevance_data.results) and not relevance_data.results[i].is_relevant:
                                url = result.get('url', 'No URL')
                                reason = relevance_data.results[i].reason
                                excluded_reasons.append(f"{url}: {reason}")
                            elif i >= len(relevance_data.results):
                                url = result.get('url', 'No URL')
                                excluded_reasons.append(f"{url}: Not evaluated by LLM (treated as not relevant)")
                        
                        logger.debug(f"Excluded {len(excluded_urls)} URLs:")
                        for reason in excluded_reasons:
                            logger.debug(f"- {reason}")
                    
                    # Ensure we have at least some results (if not, we'll keep the top 3)
                    if len(relevant_results) == 0 and len(results) > 0:
                        logger.warning("No relevant results found. Keeping top 3 results to ensure some data is returned.")
                        relevant_results = results[:min(3, len(results))]
                    
                    logger.info(f"Filtered from {len(results)} to {len(relevant_results)} relevant results")
                    return relevant_results
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error: {str(e)}")
                    logger.error(f"Raw response: {llm_response[:500]}")
                    retries += 1
                    continue
                    
                except Exception as e:
                    logger.error(f"Error validating results: {str(e)}")
                    retries += 1
                    continue
                
            except Exception as e:
                logger.error(f"Error filtering results (attempt {retries+1}/{max_retries}): {str(e)}")
                retries += 1
        
        # If all retries fail, return original results
        logger.warning(f"Failed to filter results after {max_retries} attempts. Returning all results.")
        return results

    def _run(
        self, 
        search_query: str,
        relevant_results_only: bool = False,
        **kwargs: Any
    ) -> Any:
        payload = {        
            'q': search_query,
            'format': 'json',
            'pageno': '1',
            'language': 'en-US'
        }
        response = requests.get(self.search_url, params=payload)
        if response.ok:
            results = response.json()['results']
            
            # Initialize token usage tracking
            llm_tokens_used = {"input_tokens": 0, "output_tokens": 0}
            
            # Filter for relevant results if requested
            if relevant_results_only:
                # Reset token counters before filtering
                if hasattr(self, 'token_counter_callback') and self.token_counter_callback:
                    # Store initial values in case there's already some usage
                    initial_input_tokens = getattr(self.token_counter_callback, 'input_tokens', 0)
                    initial_output_tokens = getattr(self.token_counter_callback, 'output_tokens', 0)
                    
                    logger.debug(f"Initial token counter values - Input: {initial_input_tokens}, Output: {initial_output_tokens}")
                
                logger.info(f"Filtering for relevant results from {len(results)} search results")
                results = self._filter_relevant_results(search_query, results)
                
                # Capture token usage after filtering
                if hasattr(self, 'token_counter_callback') and self.token_counter_callback:
                    # Calculate the tokens used during this operation
                    current_input_tokens = getattr(self.token_counter_callback, 'input_tokens', 0)
                    current_output_tokens = getattr(self.token_counter_callback, 'output_tokens', 0)
                    
                    llm_tokens_used["input_tokens"] = current_input_tokens - initial_input_tokens
                    llm_tokens_used["output_tokens"] = current_output_tokens - initial_output_tokens
                    
                    logger.info(f"LLM token usage - Input: {llm_tokens_used['input_tokens']}, Output: {llm_tokens_used['output_tokens']}")
            
            formatted_results = []
            for result in results:
                try:
                    engines = ', '.join(result['engines']) if 'engines' in result else 'N/A'
                    formatted_results.append('\n'.join([
                        f"Title: {result.get('title', 'No Title')}",
                        f"Link: {result.get('url', 'No Link')}",
                        f"Score: {result.get('score', 'No Score')}",
                        f"Snippet: {result.get('content', 'No Snippet')}",
                        f"Engines: {engines}",
                        f"Category: {result.get('category', 'No Category')}",
                        "---"
                    ]))
                except KeyError as e:
                    logger.warning(f"Skipping an entry due to missing key: {e}")
                    continue

            content = '\n'.join(formatted_results)
            
            # Add token usage information to the output
            token_info = ""
            if relevant_results_only and (llm_tokens_used["input_tokens"] > 0 or llm_tokens_used["output_tokens"] > 0):
                token_info = f"\n\nRelevance filtering token usage - Input: {llm_tokens_used['input_tokens']}, Output: {llm_tokens_used['output_tokens']}, Total: {llm_tokens_used['input_tokens'] + llm_tokens_used['output_tokens']}"
            
            return f"Search results:{token_info}\n{content}"
        else:
            return f"Failed to fetch search results. Status code: {response.status_code}"