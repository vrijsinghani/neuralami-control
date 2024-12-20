import os
from django.conf import settings

# Configure Django settings before imports that depend on settings
if not settings.configured:
    settings.configure(
        API_BASE_URL=os.environ.get('API_BASE_URL'),
        LITELLM_MASTER_KEY=os.environ.get('LITELLM_MASTER_KEY'),
        OPENAI_API_KEY=os.environ.get('OPENAI_API_KEY'),
        GENERAL_MODEL=os.environ.get('GENERAL_MODEL'),
        TEXT_MODEL=os.environ.get('TEXT_MODEL'),
        CODING_MODEL=os.environ.get('CODING_MODEL'),
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': 'db.sqlite3',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'apps.common',
            'apps.agents',
        ],
        USE_TZ=True,
        TIME_ZONE='America/New_York'
    )

from langchain_core.callbacks import BaseCallbackHandler
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.tools import tool
from apps.common.utils import get_llm
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_structured_chat_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import AgentExecutor, create_structured_chat_agent

class DetailedCallbackHandler(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str: str, **kwargs):
        """Handle tool start event."""
        if serialized:
            print(f"\n🛠️ Tool: {serialized.get('name', 'Unknown Tool')}")
            print(f"Input: {input_str}")

    def on_tool_end(self, output, **kwargs):
        print(f"Output: {output}")
        print("✅ Tool Complete")

    def on_agent_finish(self, finish, **kwargs):
        """Print only the final answer when agent is done."""
        print(f"\n🎯 Final Answer: {finish.return_values['output']}")
@tool
def calculator(expression: str) -> float:
    """Evaluates a mathematical expression."""
    return eval(expression)

@tool
def greeting(name: str) -> str:
    """Returns a greeting for a given name."""
    return f"Hello, {name}!"

# Get LLM instance with token tracking
llm, token_counter = get_llm(
    model_name=settings.GENERAL_MODEL,  # Use GENERAL_MODEL from settings
    temperature=0.7,

)
tools = [calculator, greeting]
# Define a system prompt template
system_prompt = '''Respond to the human as helpfully and accurately as possible. You have access to the following tools:

{tools}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).

Valid "action" values: "Final Answer" or {tool_names}

Provide only ONE action per $JSON_BLOB, as shown:

```
{{
  "action": $TOOL_NAME,
  "action_input": $INPUT
}}
```

Follow this format:

Question: input question to answer
Thought: consider previous and subsequent steps
Action:
```
$JSON_BLOB
```
Observation: action result
... (repeat Thought/Action/Observation N times)
Thought: I know what to respond
Action:
```
{{
  "action": "Final Answer",
  "action_input": "Final response to human"
}}

Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation'''

human = '''

{input}

{agent_scratchpad}

(reminder to respond in a JSON blob no matter what)'''

# Create the prompt template with the correct format
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", human),
])

# Create the agent with proper message handling
agent = create_structured_chat_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

# Update the agent executor with proper configuration
# Initialize the agent executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=False,
    handle_parsing_errors=True,
    max_iterations=3
)

callback_handler = DetailedCallbackHandler()

if __name__ == "__main__":
    # Initialize with proper message structure
    result = agent_executor.invoke(
        {
            "input": "What is 5 + 3? Then greet Alice.",
            "chat_history": [],  # Empty list for initial chat history
        },
        {"callbacks": [callback_handler, token_counter]}
    )
    #print("\nFinal Result:", result)
    print(f"\nToken Usage - Input: {token_counter.input_tokens}, Output: {token_counter.output_tokens}")
