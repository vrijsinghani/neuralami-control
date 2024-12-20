import logging
from typing import Dict, List, Optional, Any
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain_core.messages import BaseMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Manages prompt generation, formatting, and template management for chat agents.
    Consolidates prompt-related functionality from across the codebase.
    """
    
    def __init__(self, system_prompt: Optional[str] = None):
        """
        Initialize the PromptManager.
        
        Args:
            system_prompt: Optional system prompt to use as default
        """
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self.prompt_templates = {}
        self._box_width = 80

    def _get_default_system_prompt(self) -> str:
        """Get the default system prompt."""
        return """You are a helpful AI assistant. You aim to provide accurate, helpful responses
        while maintaining a professional and friendly tone. You will:
        1. Answer questions clearly and concisely
        2. Use appropriate tools when needed
        3. Admit when you don't know something
        4. Ask for clarification when needed"""

    def create_chat_prompt(self, 
                         system_prompt: Optional[str] = None,
                         additional_context: Optional[Dict] = None) -> ChatPromptTemplate:
        """
        Create a chat prompt template with system message and message history.
        
        Args:
            system_prompt: Optional override for system prompt
            additional_context: Optional additional context to include
        """
        # Create messages with system prompt and tools
        messages = [
            ("system", """
{system_prompt}

You have access to the following tools:
{tools}

Tool Names: {tool_names}

IMPORTANT INSTRUCTIONS:
1. If a tool call fails, examine the error message and try to fix the parameters
2. If multiple tool calls fail, return a helpful message explaining the limitation
3. Always provide a clear response even if data is limited
4. Never give up without providing some useful information
5. Keep responses focused and concise

To use a tool, respond with:
{{"action": "tool_name", "action_input": {{"param1": "value1", "param2": "value2"}}}}

For final responses, use:
{{"action": "Final Answer", "action_input": "your response here"}}"""),
            ("human", "{input}"),
            ("ai", "{agent_scratchpad}"),
            ("system", "Previous conversation:\n{chat_history}")
        ]
            
        # Create the prompt template
        prompt = ChatPromptTemplate.from_messages(messages)
        
        # Partial with the provided values
        return prompt.partial(
            system_prompt=system_prompt or self.system_prompt,
            tools=additional_context.get('tools', ''),
            tool_names=additional_context.get('tool_names', ''),
            chat_history=additional_context.get('chat_history', '')
        )

    def _format_context(self, context: Dict) -> str:
        """Format additional context into a string."""
        context_parts = []
        for key, value in context.items():
            if isinstance(value, (list, dict)):
                context_parts.append(f"{key}:\n{self._format_structured_value(value)}")
            else:
                context_parts.append(f"{key}: {value}")
        return "\n".join(context_parts)

    def _format_structured_value(self, value: Any, indent: int = 2) -> str:
        """Format structured values (lists/dicts) with proper indentation."""
        if isinstance(value, list):
            return "\n".join(" " * indent + f"- {item}" for item in value)
        elif isinstance(value, dict):
            return "\n".join(" " * indent + f"{k}: {v}" for k, v in value.items())
        return str(value)

    def format_chat_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Format chat history for prompt inclusion.
        Optionally truncate or summarize if too long.
        """
        return messages  # For now, return as is. Can add truncation/summarization later

    def create_tool_prompt(self, tool_name: str, tool_args: Dict) -> str:
        """Create a prompt for tool execution."""
        return f"Using tool: {tool_name}\nInput: {tool_args}"

    def create_error_prompt(self, error: str) -> str:
        """Create a prompt for error messages."""
        return f"Error occurred: {error}\nPlease try again or use a different approach."

    def register_prompt_template(self, name: str, template: str) -> None:
        """Register a new prompt template."""
        self.prompt_templates[name] = template

    def get_prompt_template(self, name: str) -> Optional[str]:
        """Get a registered prompt template."""
        return self.prompt_templates.get(name)

    def format_prompt(self, template_name: str, **kwargs) -> Optional[str]:
        """Format a registered prompt template with provided arguments."""
        template = self.get_prompt_template(template_name)
        if template:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing required argument in prompt template: {str(e)}")
            except Exception as e:
                logger.error(f"Error formatting prompt template: {str(e)}")
        return None 

    def create_agent_prompt(self, agent, client_data: Optional[Dict] = None) -> str:
        """
        Create the system prompt for the agent with client context.
        
        Args:
            agent: The agent instance
            client_data: Optional dictionary containing client information
        """
        try:
            # Base agent prompt with escaped variables
            prompt = f"""You are {agent.name}, an AI assistant.

Role: {agent.role}

Goal: {{{{goal}}}}

Backstory: {agent.backstory if hasattr(agent, 'backstory') else ''}
"""
            # Add client context if available
            if client_data:
                client_context = self._create_client_context(client_data)
                prompt += f"\n{client_context}"
            else:
                prompt += f"\nCurrent Context:\n- Current Date: {timezone.now().strftime('%Y-%m-%d')}"

            # Replace the goal placeholder with actual goal if available
            if hasattr(agent, 'goal'):
                prompt = prompt.replace('{{goal}}', agent.goal)
            else:
                prompt = prompt.replace('{{goal}}', 'Help users accomplish their tasks effectively.')

            return prompt

        except Exception as e:
            logger.error(f"Error creating agent prompt: {str(e)}", exc_info=True)
            return self._get_default_system_prompt()

    def _create_client_context(self, client_data: Dict) -> str:
        """Create formatted client context string."""
        try:
            client = client_data.get('client')
            if not client:
                return f"Current Context:\n- Current Date: {timezone.now().strftime('%Y-%m-%d')}"

            context = f"""Current Context:
- Client ID: {client.id}
- Client Name: {client.name}
- Website URL: {client.website_url}
- Target Audience: {client.target_audience or 'N/A'}
- Current Date: {timezone.now().strftime('%Y-%m-%d')}

IMPORTANT: When using tools that require client_id, always use {client.id} as the client_id parameter.
"""
            # Add business objectives if present
            if client.business_objectives:
                objectives_text = "\n".join([f"- {obj}" for obj in client.business_objectives])
                context += f"\n\nBusiness Objectives:\n{objectives_text}"

            # Add client profile if available
            if client.client_profile:
                context += f"\n\nClient Profile:\n{client.client_profile}"

            return self._create_box(context, "🔍 CLIENT CONTEXT")

        except Exception as e:
            logger.error(f"Error creating client context: {str(e)}", exc_info=True)
            return f"Current Context:\n- Current Date: {timezone.now().strftime('%Y-%m-%d')}"

    def _create_box(self, content: str, title: str = "") -> str:
        """Create a pretty ASCII box with content for logging."""
        lines = []
        width = self._box_width
        
        # Top border with title
        if title:
            title = f" {title} "
            padding = (width - len(title)) // 2
            lines.append("╔" + "═" * padding + title + "═" * (width - padding - len(title)) + "╗")
        else:
            lines.append("╔" + "═" * width + "╗")
            
        # Content
        for line in content.split('\n'):
            # Split long lines
            while len(line) > width:
                split_at = line[:width].rfind(' ')
                if split_at == -1:
                    split_at = width
                lines.append("║ " + line[:split_at].ljust(width-2) + " ║")
                line = line[split_at:].lstrip()
            lines.append("║ " + line.ljust(width-2) + " ║")
            
        # Bottom border
        lines.append("╚" + "═" * width + "╝")
        
        return "\n".join(lines)