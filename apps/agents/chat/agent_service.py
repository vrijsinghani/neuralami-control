from typing import Optional, Tuple, Any
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage, AIMessage, HumanMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.language_models import BaseLanguageModel
from langchain.tools import BaseTool
from langchain.agents import create_json_chat_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from apps.common.utils import get_llm
from apps.agents.utils import get_tool_classes
from apps.agents.chat.history import DjangoCacheMessageHistory
from apps.seo_manager.models import Client

from channels.db import database_sync_to_async
import json
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

class AgentService:
    """Unified service for agent creation and chat handling"""
    
    def __init__(self, agent, model_name: str, client_data: dict, 
                 callback_handler: Any, session_id: Optional[str] = None):
        self.agent = agent
        self.model_name = model_name
        self.client_id = client_data.get('client_id') if client_data else None
        self.callback_handler = callback_handler
        self.session_id = session_id or f"{agent.id}_{self.client_id if self.client_id else 'no_client'}"
        
        # Will be initialized later
        self.llm: Optional[BaseLanguageModel] = None
        self.agent_executor: Optional[AgentExecutor] = None
        self.processing: bool = False
        self.message_history: Optional[DjangoCacheMessageHistory] = None

    async def initialize(self) -> None:
        """Initialize the agent with LLM, tools, and memory"""
        try:
            # Initialize LLM
            self.llm, _ = get_llm(
                model_name=self.model_name,
                temperature=0.0,
                streaming=True
            )

            # Initialize message history
            self.message_history = DjangoCacheMessageHistory(
                session_id=self.session_id,
                ttl=3600
            )

            # Load tools and create agent
            tools = await self._load_tools()
            system_prompt = await self._create_system_prompt()
            agent = self._create_agent(tools, system_prompt)
            
            # Create agent executor with memory
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=self.message_history,
                verbose=True,
                max_iterations=5,
                early_stopping_method="force",
                handle_parsing_errors=True,
                return_intermediate_steps=True
            )

        except Exception as e:
            logger.error(f"Error initializing agent service: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Process a user message and stream the response"""
        if not self.agent_executor or self.processing:
            return

        try:
            self.processing = True
            
            # Handle message editing by clearing recent history
            if is_edit:
                await self._clear_recent_history()
            
            # Process message and stream response
            async for chunk in self.agent_executor.astream(
                {"input": message},
                {"configurable": {"session_id": self.session_id}}
            ):
                await self._process_chunk(chunk)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await self.callback_handler.on_llm_error(f"Error: {str(e)}")
        finally:
            self.processing = False

    def _create_agent(self, tools: list[BaseTool], system_prompt: str) -> Any:
        """Create the agent with proper prompt template"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_system_template()),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ]).partial(system_prompt=system_prompt)

        return create_json_chat_agent(
            llm=self.llm,
            tools=tools,
            prompt=prompt
        )

    @staticmethod
    def _get_system_template() -> str:
        """Return the system template for the agent"""
        return """
{system_prompt}

Tools available: {tools}
Tool Names: {tool_names}

INSTRUCTIONS:
1. Use tools to gather information when needed
2. Provide clear responses even with limited data
3. Handle errors gracefully and retry with corrected parameters

RESPONSE FORMAT (JSON only):
1. Tool calls: {"action":"tool_name","action_input":{"param":"value"}}
2. Final answers: {"action":"Final Answer","action_input":"response"}

Rules:
- Use exact JSON format shown
- No additional text or formatting
- Action must be a tool name or "Final Answer"
- One action per response
"""

    async def _process_chunk(self, chunk: Any) -> None:
        """Process a response chunk from the agent"""
        try:
            if isinstance(chunk, dict):
                if "output" in chunk:
                    await self.callback_handler.on_llm_new_token(chunk["output"])
                elif "intermediate_steps" in chunk:
                    await self._process_tool_steps(chunk["intermediate_steps"])
            elif isinstance(chunk, str) and chunk.strip():
                await self.callback_handler.on_llm_new_token(chunk)
                
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")

    # ... (keeping existing tool loading and system prompt creation methods)
    # The tool handling is complex because it needs to:
    # 1. Handle structured and unstructured tools
    # 2. Format tool outputs consistently
    # 3. Support async execution
    # 4. Maintain proper error handling
 