import os
from typing import Any, Type, List, Dict
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
from apps.agents.tools.searxng_tool.searxng_tool import SearxNGSearchTool
from apps.agents.tools.browser_tool.browser_tool import BrowserTool
from apps.common.utils import get_llm as utils_get_llm
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
import logging

logger = logging.getLogger(__name__)

class SearchContextToolSchema(BaseModel):
    """Input schema for SearchContextTool."""
    question: str = Field(..., description="The user's question to research and answer.")

class SearchContextTool(BaseTool):
    name: str = "Search and provide contextual answer"
    description: str = "Searches the internet, gathers context from multiple sources, and provides a detailed answer with follow-up questions."
    args_schema: Type[BaseModel] = SearchContextToolSchema
    
    # Define the tools as fields
    search_tool: SearxNGSearchTool = Field(default_factory=SearxNGSearchTool)
    browser_tool: BrowserTool = Field(default_factory=BrowserTool)
    model_name: str = Field(default="anthropic/claude-3-haiku-20240307")
    llm: Any = None
    token_counter_callback: Any = None

    def __init__(self, **data):
        super().__init__(**data)
        self.llm, self.token_counter_callback = utils_get_llm(self.model_name, temperature=0.7)

# Add this method to the SearchContextTool class:
    def _reformulate_question(self, original_question: str) -> str:
        "Reformulate the user's question into an optimized search query."
        
        reformulation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at reformulating questions into optimal search queries. 
            Your task is to analyze the user's question and create a more effective search query that will yield the most relevant results.
            
            Follow these guidelines:
            1. Identify Core Concepts:
                - Extract the main topics and key concepts
                - Identify any implicit assumptions or context
            
            2. Add Critical Context:
                - Include relevant technical terms
                - Add synonyms for important concepts
                - Specify time period if relevant (e.g., "2024", "recent", "latest")
            
            3. Optimize for Search:
                - Use boolean operators when helpful (AND, OR)
                - Include specific phrases in quotes for exact matches
                - Remove unnecessary words (articles, prepositions)
                - Add clarifying terms to disambiguate
            
            4. Enhance Specificity:
                - Add domain-specific terminology
                - Include relevant qualifiers
                - Specify desired information type (research, news, analysis, etc.)
            
            Return only the reformulated search query, without explanation or additional text."""),
            ("human", """Original question: {question}
            
            Create an optimized search query that will find the most relevant and comprehensive information to answer this question.""")
        ])

        reformulation_chain = reformulation_prompt | self.llm | StrOutputParser()

        try:
            optimized_query = reformulation_chain.invoke({
                'question': original_question
            })
            logger.info(f"Reformulated question: {optimized_query}")
            return optimized_query
        except Exception as e:
            logger.error(f"Error reformulating question: {str(e)}")
            return original_question

# Then modify the _run method to use the reformulated question:

    def _extract_urls(self, search_results: str) -> List[str]:
        """Extract URLs from search results."""
        urls = []
        for line in search_results.split('\n'):
            if line.startswith('Link: '):
                urls.append(line.replace('Link: ', '').strip())
        return urls[:6]  # Get top 6 results

    def _gather_context(self, urls: List[str]) -> str:
        """Gather context from URLs."""
        contexts = []
        for url in urls:
            try:
                content = self.browser_tool._run(website=url)
                if content and len(content) > 100:  # Basic validation
                    contexts.append(f"Source ({url}):\n{content}")
            except Exception as e:
                logger.error(f"Error scraping {url}: {str(e)}")
        return "\n\n".join(contexts)

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using LLM."""
        answer_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful AI assistant. Using the provided context, 
            answer the user's question thoroughly and accurately. Cite sources when possible.
            Format your response in markdown."""),
            ("human", """
            Question: {question}
            
            Context: {context}
            
            Please provide a detailed answer based on the context provided.
            """)
        ])
        
        answer_chain = answer_prompt | self.llm | StrOutputParser()
        return answer_chain.invoke({
            'question': question,
            'context': context
        })

    def _generate_follow_up_questions(self, question: str, answer: str) -> List[str]:
        """Generate follow-up questions based on the answer."""
        followup_prompt = ChatPromptTemplate.from_messages([
            ("system", """Based on the original question and answer provided, 
            generate exactly 3 relevant follow-up questions that would help explore 
            the topic further. Format as a markdown list."""),
            ("human", """
            Original Question: {question}
            Answer: {answer}
            
            Generate 3 follow-up questions:
            """)
        ])
        
        followup_chain = followup_prompt | self.llm | StrOutputParser()
        return followup_chain.invoke({
            'question': question,
            'answer': answer
        })

    def _run(
        self,
        question: str,
        **kwargs: Any
        ) -> Any:
        """Execute the search context tool pipeline."""
        try:
            # 0. Reformulate the question for better search results
            optimized_query = self._reformulate_question(question)
            logger.info(f"Original question: {question}")
            logger.info(f"Optimized query: {optimized_query}")
            
            # 1. Search for relevant results using optimized query
            search_results = self.search_tool._run(search_query=optimized_query)
            
            # 2. Extract URLs and gather context
            urls = self._extract_urls(search_results)
            context = self._gather_context(urls)
            
            # 3. Generate answer (using original question for better context)
            answer = self._generate_answer(question, context)
            
            # 4. Generate follow-up questions
            follow_up = self._generate_follow_up_questions(question, answer)
            
            # 5. Format and return results
            result = {
                "original_question": question,
                "optimized_query": optimized_query,
                "answer": answer,
                "follow_up_questions": follow_up,
                "sources": urls
            }
            
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error in SearchContextTool: {str(e)}")
            return f"An error occurred while processing your request: {str(e)}"