# Token Tracking and Counting with `get_llm()`

This guide explains how to track and count tokens when using Language Models (LLMs) through the `get_llm()` utility function.

## Overview

Token counting is essential for:
- Monitoring computational resource usage
- Managing costs (as most LLM providers charge based on token usage)
- Ensuring responses stay within token limits
- Performance optimization and debugging

## How Token Counting Works

In our system, token counting is implemented via a callback mechanism that hooks into the LangChain LLM calls:

1. When an LLM processes input (prompts), the `on_llm_start` callback captures and counts input tokens
2. When an LLM returns output (generations), the `on_llm_end` callback captures and counts output tokens
3. These counts are maintained in a `TokenCounterCallback` instance that's returned alongside the LLM

## Getting Started

### Basic Usage

To get an LLM with token counting capability:

```python
from apps.common.utils import get_llm
from langchain.schema import HumanMessage

# Get LLM with token counter
llm, token_counter = get_llm("anthropic/claude-3-haiku-latest", temperature=0.7)

# Make an LLM call
response = llm.invoke([HumanMessage(content="Tell me a joke.")])

# Check token usage
input_tokens = token_counter.input_tokens
output_tokens = token_counter.output_tokens
total_tokens = input_tokens + output_tokens

print(f"Input tokens: {input_tokens}")
print(f"Output tokens: {output_tokens}")
print(f"Total tokens: {total_tokens}")
```

### Inside Custom Tools

When implementing custom tools that use LLMs:

```python
from apps.common.utils import get_llm

class MyCustomTool:
    def __init__(self, **data):
        # Initialize LLM and token counter
        self.llm, self.token_counter_callback = get_llm("anthropic/claude-3-haiku-latest")
        # Define token tracking fields
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
    def _update_token_counters(self):
        """Update total token counts from the token counter callback"""
        if hasattr(self, 'token_counter_callback') and self.token_counter_callback:
            current_input = getattr(self.token_counter_callback, 'input_tokens', 0)
            current_output = getattr(self.token_counter_callback, 'output_tokens', 0)
            
            # Calculate incremental usage since last check
            input_diff = current_input - self.total_input_tokens
            output_diff = current_output - self.total_output_tokens
            
            if input_diff > 0 or output_diff > 0:
                print(f"Token usage - Input: +{input_diff}, Output: +{output_diff}")
                
            # Update totals
            self.total_input_tokens = current_input
            self.total_output_tokens = current_output
        
        return self.total_input_tokens, self.total_output_tokens
        
    def use_llm(self, prompt):
        # Make LLM call
        response = self.llm.invoke([HumanMessage(content=prompt)])
        
        # Update token counters after call
        self._update_token_counters()
        
        return response.content
```

For Pydantic-based tools (like those inheriting from `BaseTool`), define token fields properly:

```python
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

class MyPydanticTool(BaseTool):
    name: str = "My Tool"
    description: str = "A tool that uses LLMs with token tracking"
    args_schema: Type[BaseModel] = MyToolSchema
    
    # Define token tracking fields as proper Pydantic fields with default values
    total_input_tokens: int = Field(0, description="Total input tokens used")
    total_output_tokens: int = Field(0, description="Total output tokens used")
    
    def __init__(self, **data):
        super().__init__(**data)
        self.llm, self.token_counter_callback = get_llm("anthropic/claude-3-haiku-latest")
        # No need to initialize token counters here as they're defined in the class
```

## Tracking Token Usage Before and After Operations

For specific operations, you may want to track token usage increments:

```python
# Store initial values
initial_input_tokens = getattr(self.token_counter_callback, 'input_tokens', 0)
initial_output_tokens = getattr(self.token_counter_callback, 'output_tokens', 0)

# Perform operation with LLM
result = self.llm.invoke([HumanMessage(content="Some prompt")])

# Calculate tokens used for this operation
current_input_tokens = getattr(self.token_counter_callback, 'input_tokens', 0)
current_output_tokens = getattr(self.token_counter_callback, 'output_tokens', 0)

operation_input_tokens = current_input_tokens - initial_input_tokens
operation_output_tokens = current_output_tokens - initial_output_tokens
operation_total_tokens = operation_input_tokens + operation_output_tokens

print(f"Operation used {operation_total_tokens} tokens ({operation_input_tokens} input, {operation_output_tokens} output)")
```

## Tracking Tokens Across Sub-Tools

When your tool uses other tools that also make LLM calls, you need to extract and accumulate their token usage to get accurate totals:

```python
class MainTool:
    def __init__(self):
        self.llm, self.token_counter = get_llm(model_name)
        self.subtool_a = SubToolA()  # Has its own LLM and token counter
        self.subtool_b = SubToolB()  # Has its own LLM and token counter
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
    def _extract_subtool_tokens(self, subtool_result):
        """Extract token usage from a sub-tool's result."""
        try:
            # Parse the result to find token information
            # This depends on how your sub-tool reports token usage
            result_data = json.loads(subtool_result)
            input_tokens = result_data.get("llm_input_tokens", 0)
            output_tokens = result_data.get("llm_output_tokens", 0)
            return input_tokens, output_tokens
        except Exception as e:
            logger.error(f"Error extracting token usage: {str(e)}")
            return 0, 0
            
    def _update_token_counters_from_subtool(self, input_tokens, output_tokens):
        """Add sub-tool token usage to main tool's totals."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        logger.debug(f"Added sub-tool usage - Input: +{input_tokens}, Output: +{output_tokens}")
        
    def run(self):
        # Use sub-tools
        subtool_a_result = self.subtool_a.run(...)
        
        # Extract and accumulate tokens from sub-tool A
        input_tokens, output_tokens = self._extract_subtool_tokens(subtool_a_result)
        self._update_token_counters_from_subtool(input_tokens, output_tokens)
        
        # Make direct LLM call
        response = self.llm.invoke([HumanMessage(content="Process this...")])
        
        # Update totals with our own LLM usage
        self._update_token_counters()
        
        # Use another sub-tool
        subtool_b_result = self.subtool_b.run(...)
        
        # Extract and accumulate tokens from sub-tool B
        input_tokens, output_tokens = self._extract_subtool_tokens(subtool_b_result)
        self._update_token_counters_from_subtool(input_tokens, output_tokens)
        
        # Return comprehensive token usage
        return {
            "result": result,
            "token_usage": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens
            }
        }
```

### Real-World Example: DeepResearchTool

The DeepResearchTool demonstrates comprehensive token tracking across multiple sub-tools:

1. It extracts token usage from CompressionTool:
   ```python
   compression_result = self.compression_tool._run(...)
   input_tokens, output_tokens = self._extract_compression_tool_tokens(compression_result)
   self._update_token_counters_from_subtool(input_tokens, output_tokens)
   ```

2. It extracts token usage from SearxNGTool:
   ```python
   search_results = self.search_tool._run(...)
   input_tokens, output_tokens = self._extract_searxng_tool_tokens(search_results)
   self._update_token_counters_from_subtool(input_tokens, output_tokens)
   ```

3. It includes all token usage in its final report:
   ```python
   metadata_section = f"""
   ## Research Metadata
   ...
   - **Token Usage (Comprehensive):**
     - Input Tokens: {final_input_tokens:,}
     - Output Tokens: {final_output_tokens:,}
     - Total Tokens: {final_input_tokens + final_output_tokens:,}
     - Note: Includes all LLM calls, sub-tools, and filtering operations
   """
   ```

## Including Token Usage in Reports

Token usage information can be included in tool outputs or reports:

```python
# Get final token counts
final_input_tokens, final_output_tokens = self._update_token_counters()

# Add token usage to report metadata
metadata_section = f"""
## Token Usage
- Input Tokens: {final_input_tokens:,}
- Output Tokens: {final_output_tokens:,}
- Total Tokens: {final_input_tokens + final_output_tokens:,}
"""

# Append metadata to report
final_report = content + "\n\n" + metadata_section
```

## Best Practices

1. **Reset Counters at Start**: Reset token counters at the beginning of operations:
   ```python
   self.token_counter_callback.input_tokens = 0
   self.token_counter_callback.output_tokens = 0
   ```

2. **Update After LLM Calls**: Always update counters after LLM calls to ensure accurate tracking:
   ```python
   response = self.llm.invoke([HumanMessage(content=prompt)])
   self._update_token_counters()  # Update after call
   ```

3. **Log Incremental Usage**: Monitor incremental token usage for debugging:
   ```python
   prev_input = self.total_input_tokens
   prev_output = self.total_output_tokens
   
   # After operation
   self._update_token_counters()
   logger.debug(f"Operation used {self.total_input_tokens - prev_input} input tokens and {self.total_output_tokens - prev_output} output tokens")
   ```

4. **Include in Final Results**: Always include token usage in final results for transparency and cost tracking.

## Troubleshooting

### Zero Token Counts

If token counters remain at zero after LLM calls:

1. **Check LLM Initialization**: Ensure the token counter is properly attached to the LLM:
   ```python
   # Correct initialization
   llm, token_counter = get_llm(model_name)
   ```

2. **Verify Callbacks**: Ensure the token counter callback is properly attached to the LLM:
   ```python
   # Inside get_llm()
   llm = ChatOpenAI(
       model=model_name,
       temperature=temperature,
       callbacks=[token_counter],  # Correct callback attachment
   )
   ```

3. **Debug with Simple Test**: Create a simple test to verify token counting:
   ```python
   llm, token_counter = get_llm(model_name)
   print(f"Initial: {token_counter.input_tokens}, {token_counter.output_tokens}")
   response = llm.invoke([HumanMessage(content="Test")])
   print(f"After: {token_counter.input_tokens}, {token_counter.output_tokens}")
   ```

### Token Counts Not Updating

If token counts aren't updating properly:

1. **Check for Callback Deprecations**: LangChain sometimes changes callback interfaces. Ensure using the current parameter name:
   ```python
   # Modern LangChain uses 'callbacks' instead of 'callback_manager'
   llm = ChatOpenAI(
       callbacks=[token_counter],  # Correct parameter
   )
   ```

2. **Verify Token Counter Implementation**: Check that the callback methods match LangChain's expected signatures:
   ```python
   def on_llm_start(self, serialized, prompts, **kwargs):
       # Method signature must match what LangChain expects
   ```

## Implementation Details

The token counting implementation consists of:

1. **TokenCounterCallback Class**: A LangChain callback handler that tracks tokens:
   ```python
   class TokenCounterCallback(BaseCallbackHandler):
       def __init__(self, tokenizer):
           self.input_tokens = 0
           self.output_tokens = 0
           self.tokenizer = tokenizer

       def on_llm_start(self, serialized, prompts, **kwargs):
           for prompt in prompts:
               self.input_tokens += len(self.tokenizer.encode(prompt, disallowed_special=()))

       def on_llm_end(self, response, **kwargs):
           for generation in response.generations:
               for result in generation:
                   self.output_tokens += len(self.tokenizer.encode(result.text, disallowed_special=()))
   ```

2. **get_llm Function**: Creates both the LLM and token counter, connecting them:
   ```python
   def get_llm(model_name: str, temperature: float = 0.7, streaming: bool = False):
       # Initialize tokenizer and token counter
       tokenizer = tiktoken.get_encoding("cl100k_base")
       token_counter = TokenCounterCallback(tokenizer)
       
       # Create a callback manager with the token counter
       callback_manager = CallbackManager([token_counter])
       
       # Initialize ChatOpenAI with proxy settings and callback manager
       llm = ChatOpenAI(
           model=model_name,
           temperature=temperature,
           streaming=streaming,
           base_url=settings.API_BASE_URL,
           api_key=settings.LITELLM_MASTER_KEY,
           callbacks=[token_counter],  # Use callbacks instead of callback_manager
       )
       
       return llm, token_counter
   ```

This implementation ensures accurate token counting for both input and output across LLM operations. 