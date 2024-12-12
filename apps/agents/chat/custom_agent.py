from typing import Sequence
from langchain_core.messages import SystemMessage
from langchain.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel
from langchain.agents import create_structured_chat_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import logging

logger = logging.getLogger(__name__)

def create_custom_agent(
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    system_prompt: str
) -> any:
    """Create a JSON chat agent with the configured tools and LLM."""
    
    # Create the system message template
    system_template = """
{system_prompt}

As an AI assistant, you have access to the following tools:
{tools}

Tool Name: {tool_names}

IMPORTANT INSTRUCTIONS:
1. If a tool call fails, examine the error message and try to fix the parameters
2. If multiple tool calls fail, return a helpful message explaining the limitation
3. Always provide a clear response even if data is limited
4. Never give up without providing some useful information
5. Keep responses focused and concise
6. Use previous conversation context to provide more relevant responses

RESPONSE FORMAT:
You must respond with ONLY a JSON object in one of these two formats:

1. Tool call format (exact format required):
{{"action":"tool_name","action_input":{{"param1":"value1","param2":"value2"}}}}

2. Final answer format (exact format required):
{{"action":"Final Answer","action_input":"Your response here"}}

IMPORTANT RULES:
- Use ONLY the exact JSON formats shown above
- NO additional text, formatting, or explanation
- NO line breaks or pretty printing
- NO markdown or code blocks
- The action must be one of: {tool_names} or "Final Answer"
- Double quotes are required for all keys and string values
- Provide only ONE action per response"""

    # Create the prompt template with chat history
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_template),
        MessagesPlaceholder(variable_name="chat_history"),  # Include chat history
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    # Partial the prompt with the system prompt
    prompt = prompt.partial(system_prompt=system_prompt)
    logger.debug(f"CustomAgent Prompt: {prompt}")
    
    # Create and return the agent
    return create_structured_chat_agent(
        llm=llm,
        tools=tools,
        prompt=prompt
    )