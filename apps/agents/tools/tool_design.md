# Tool Design Guidelines

This document outlines the standard patterns and best practices for creating tools in our agent system.

## Basic Tool Structure

### 1. Tool Components
Every tool should have these key components:
- Schema class (inherits from `pydantic.BaseModel`)
- Tool class (inherits from `crewai.tools.BaseTool`) 
- Proper logging configuration
- Error handling

### 2. Standard Imports
```{{python}}
from typing import Dict, Any, Type, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import logging
from django.conf import settings
logger = logging.getLogger(__name__)
```

## Schema Definition

### 1. Input Schema
- Create a Pydantic model class named `{{ToolName}}Schema`
- Use descriptive Field annotations with proper typing
- Include clear field descriptions

Example:

```{{python}}
class ExampleToolSchema(BaseModel):
    """Input schema for ExampleTool."""
    input_field: str = Field(
        ...,  # ... means required
        description="Clear description of what this field does"
    )
    optional_field: Optional[str] = Field(
        None,
        description="Description of optional field"
    )
```

## Tool Implementation

### 1. Tool Class Structure
```{{python}}
class ExampleTool(BaseTool):
    name: str = "Example Tool"
    description: str = """
    Detailed description of what the tool does,
    its capabilities, and expected usage.
    """
    args_schema: Type[BaseModel] = ExampleToolSchema

    def _run(self, **kwargs: Any) -> dict:
        try:
            # Instantiate and validate input parameters using the Pydantic schema
            params = self.args_schema(**kwargs)
            # Tool implementation using validated parameters
            result = perform_operation()
            
            logger.debug(f"Tool execution result: {str(result)[:200]}...")
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
```

### 2. Key Implementation Points
- Use the `args_schema` attribute to specify a Pydantic model for input validation.
- Accept parameters using `**kwargs` in the `_run()` method and instantiate the schema with these parameters (e.g., `params = self.args_schema(**kwargs)`).
- Return a dictionary that is JSON-serializable with a structured response, typically including a boolean key `success` and keys such as `data` or `error`.
- Implement proper error handling: catch exceptions, log errors with `exc_info=True` for stack traces, and return a structured error response.
- Use type hints consistently and include logging for important operations.

## Best Practices

### 1. Input Validation
- Use Pydantic schemas for automatic input validation
- Define clear field constraints and types
- Handle input preprocessing when needed

### 2. Error Handling
```{{python}}
try:
    # Tool logic
    result = perform_operation()
    return json.dumps(result)
except Exception as e:
    logger.error(f"Error in {{self.name}}: {{str(e)}}")
    return json.dumps({{
        "error": "Operation failed",
        "message": str(e)
    }})
```

### 3. Logging
- Configure proper logging for debugging and monitoring
- Log important operations and errors
- Include relevant context in log messages

### 4. Output Formatting
- Return structured JSON responses
- Clean and validate output before returning
- Handle special characters and formatting

## Example Tool Template

```{{python}}
from typing import Any, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging

logger = logging.getLogger(__name__)

class NewToolSchema(BaseModel):
    """Input schema for NewTool."""
    input_param: str = Field(
        ...,
        description="Description of the input parameter"
    )
    optional_field: str = Field(
        None,
        description="Description of the optional parameter"
    )

class NewTool(BaseTool):
    name: str = "New Tool"
    description: str = """
    Detailed description of the tool's purpose and functionality.
    """
    args_schema: Type[BaseModel] = NewToolSchema

    def _run(self, **kwargs: Any) -> dict:
        try:
            # Validate inputs using the schema
            params = self.args_schema(**kwargs)
            result = self._process_input(params.input_param, params.optional_field)
            logger.debug(f"Tool execution result: {result}")
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _process_input(self, input_param: str, optional_field: str = None) -> dict:
        # Helper method for processing
        pass
```

## Common Pitfalls to Avoid

1. **Input Validation and Schema Mismatch**
   - ❌ Avoid mismatches between schema field names and how you reference them in your `_run()` method.
   - ✅ Ensure that all necessary fields are defined in your Pydantic schema and that you instantiate the schema with `**kwargs` to automatically enforce validation.

2. **Error Handling**
   - ❌ Don't let exceptions propagate unhandled.
   - ✅ Always catch exceptions, log them with appropriate context (using `exc_info=True`), and return a structured error response.

3. **Output Formatting**
   - ❌ Don't return a raw JSON string; instead, return a Python dictionary with keys like `success`, `data`, and `error`.
   - ✅ Ensure your response is JSON-serializable so that the caller can easily convert it if needed.

4. **Parameter Handling**
   - ✅ Using `**kwargs` in the `_run()` method is acceptable when combined with Pydantic schema instantiation. This pattern reduces boilerplate and improves maintainability.

5. **Logging**
   - Configure logging appropriately and include relevant context in your log messages for easier debugging and tracing.

## Testing Tools

1. Create unit tests for your tool
2. Test with various input combinations
3. Verify error handling
4. Check output format consistency
5. Validate schema enforcement

## Integration with Task System

Tools are executed through the task system, which:
1. Validates inputs against the schema
2. Processes input types appropriately
3. Handles async/sync execution
4. Manages tool state and logging

Remember to test your tool through the task system to ensure proper integration.

