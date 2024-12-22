Title: Tool Development Guide
Description: Template and guidelines for creating new tools following the Google Analytics tool structure, with proper error handling, data processing, and configuration.
Body:

## Tool Structure

### 1. Base Components

```python
import logging
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from crewai_tools.tools.base_tool import BaseTool
from enum import Enum

logger = logging.getLogger(__name__)
```

### 2. Request Model

```python
class DataFormat(str, Enum):
    """Enum for data output formats"""
    RAW = "raw"
    SUMMARY = "summary"
    COMPACT = "compact"

class ToolRequest(BaseModel):
    """Input schema for the tool."""
    
    # Required parameters
    primary_param: type = Field(
        description="Parameter description"
    )
    
    # Optional parameters with defaults
    data_format: DataFormat = Field(
        default=DataFormat.RAW,
        description="""
        How to format the returned data:
        - 'raw': Returns all data points
        - 'summary': Returns statistical summary
        - 'compact': Returns top N results
        """
    )
    
    @field_validator("primary_param")
    @classmethod
    def validate_param(cls, value: type) -> type:
        """Validate the primary parameter"""
        # Add validation logic here
        return value
```

### 3. Tool Implementation

```python
class CustomTool(BaseTool):
    name: str = "Tool Display Name"
    description: str = """
    Detailed tool description with:
    
    Key Features:
    - Feature 1
    - Feature 2
    
    Example Commands:
    1. Basic usage:
       tool._run(basic_example)
    
    2. Advanced usage:
       tool._run(advanced_example)
    """
    args_schema: Type[BaseModel] = ToolRequest
    
    def __init__(self, **kwargs):
        super().__init__()
        logger.info("Tool initialized")
        self._initialize_components()

    def _initialize_components(self):
        """Initialize tool components and configurations"""
        pass

    def _run(self,
             primary_param: type,
             data_format: DataFormat = DataFormat.RAW,
             **kwargs) -> dict:
        """
        Main execution method for the tool.
        
        Args:
            primary_param: Primary parameter description
            data_format: Output format specification
            **kwargs: Additional optional parameters
            
        Returns:
            dict: {
                'success': bool,
                'data': List[dict] or dict,
                'error': Optional[str]
            }
        """
        try:
            request_params = ToolRequest(
                primary_param=primary_param,
                data_format=data_format,
                **kwargs
            )
            
            result = self._process_request(request_params)
            
            return {
                'success': True,
                'data': result
            }

        except Exception as e:
            logger.error(f"Error in tool: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def _process_request(self, params: ToolRequest) -> List[dict]:
        """Process the request parameters and generate results"""
        pass
```

### 4. Data Processing

```python
class DataProcessor:
    """Helper class for data processing operations"""
    
    @staticmethod
    def process_data(data: List[dict], params: ToolRequest) -> List[dict]:
        """Process the raw data based on request parameters"""
        pass

    @staticmethod
    def _generate_summary(data: List[dict]) -> dict:
        """Generate statistical summary of the data"""
        pass
```

## Implementation Guidelines

### 1. Request Model Design
- Use clear, descriptive parameter names
- Add comprehensive field descriptions
- Implement field validators for data validation
- Group related parameters logically
- Use appropriate field types and constraints

### 2. Error Handling
- Catch and log specific exceptions
- Provide meaningful error messages
- Include context in error logs
- Return graceful failure responses
- Maintain consistent error format

### 3. Data Processing
- Separate processing logic from tool interface
- Implement data transformations in DataProcessor
- Support multiple output formats
- Add data validation and cleaning
- Include performance optimizations

### 4. Documentation
- Write clear docstrings
- Include usage examples
- Document return formats
- Explain error scenarios
- Add parameter descriptions

### 5. Testing Considerations
- Test error handling
- Validate input parameters
- Check output formats
- Test edge cases
- Verify data processing

## Best Practices

1. **Input Validation**
   - Validate all input parameters
   - Use Pydantic validators
   - Handle edge cases
   - Provide clear error messages

2. **Error Handling**
   - Use specific exception types
   - Log with context
   - Return consistent error format
   - Include stack traces in logs

3. **Performance**
   - Optimize data processing
   - Use appropriate data structures
   - Implement caching when needed
   - Handle large datasets efficiently

4. **Maintainability**
   - Follow consistent naming conventions
   - Separate concerns
   - Document complex logic
   - Use type hints

5. **Testing**
   - Write unit tests
   - Test error scenarios
   - Validate output formats
   - Check edge cases

## Example Usage

```python
# Initialize the tool
tool = CustomTool()

# Basic usage
result = tool._run(
    primary_param=value,
    data_format=DataFormat.RAW
)

# Advanced usage with additional parameters
result = tool._run(
    primary_param=value,
    data_format=DataFormat.SUMMARY,
    **additional_params
)

# Error handling example
try:
    result = tool._run(primary_param=value)
    if not result['success']:
        logger.error(f"Tool execution failed: {result['error']}")
except Exception as e:
    logger.error(f"Unexpected error: {str(e)}", exc_info=True)
``` 