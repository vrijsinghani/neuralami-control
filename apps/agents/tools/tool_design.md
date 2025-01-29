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

    def _run(self, input_field: str, optional_field: Optional[str] = None) -> str:
        try:
            # Tool implementation
            pass
        except Exception as e:
            logger.error(f"Error in ExampleTool: {{str(e)}}")
            return json.dumps({{
                "error": "Operation failed",
                "message": str(e)
            }})
```

### 2. Key Implementation Points
- Always define explicit parameters in `_run()` method (avoid `**kwargs`)
- Parameters must match schema field names exactly
- Return JSON-serializable responses
- Implement proper error handling and logging
- Use type hints consistently

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
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import logging

logger = logging.getLogger(__name__)

class NewToolSchema(BaseModel):
    """Input schema for NewTool."""
    input_param: str = Field(
        ...,
        description="Description of the input parameter"
    )

class NewTool(BaseTool):
    name: str = "New Tool"
    description: str = """
    Detailed description of the tool's purpose and functionality.
    """
    args_schema: Type[BaseModel] = NewToolSchema

    def _run(self, input_param: str) -> str:
        try:
            # Tool implementation
            result = self._process_input(input_param)
            
            logger.debug(f"Tool execution result: {{result[:200]}}...")
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error in {{self.name}}: {{str(e)}}")
            return json.dumps({{
                "error": "Operation failed",
                "message": str(e)
            }})

    def _process_input(self, input_param: str) -> dict:
        # Helper method for processing
        pass
```

## Common Pitfalls to Avoid

1. **Kwargs Usage**
   - ❌ Don't use `**kwargs` in `_run()`
   - ✅ Use explicit parameters matching schema fields

2. **Schema Mismatch**
   - ❌ Don't have mismatched parameter names between schema and `_run()`
   - ✅ Ensure schema field names exactly match `_run()` parameters

3. **Error Handling**
   - ❌ Don't let exceptions propagate unhandled
   - ✅ Catch exceptions and return structured error responses

4. **Type Safety**
   - ❌ Don't use dynamic typing or ignore type hints
   - ✅ Use proper type hints and Pydantic validation

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

