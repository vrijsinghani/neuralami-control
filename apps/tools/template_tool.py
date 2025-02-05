"""
Generic Template Tool

This module provides a base template for creating new tools with standardized structure.
It includes a basic request schema and tool implementation pattern.
"""

import logging
from typing import Any, Type, List, Optional
from pydantic import (
    BaseModel,
    Field,
    field_validator
)
from crewai.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

class TemplateToolRequest(BaseModel):
    """Schema for Template Tool data requests."""
    
    class Config:
        """Pydantic config"""
        use_enum_values = True
        extra = "forbid"
    
    # Example fields - modify according to your needs
    input_text: str = Field(
        ...,  # ... means required
        description="Primary input text for the tool"
    )
    
    max_results: int = Field(
        default=10,
        description="Maximum number of results to return",
        gt=0,
        le=100
    )
    
    include_metadata: bool = Field(
        default=False,
        description="Whether to include additional metadata in the response"
    )
    
    @field_validator("input_text")
    @classmethod
    def validate_input_text(cls, value: str) -> str:
        """Validate input text is not empty"""
        if not value.strip():
            raise ValueError("Input text cannot be empty")
        return value.strip()

class TemplateTool(BaseTool):
    """
    Template Tool base implementation.
    
    This provides a standard structure for implementing new tools.
    Customize the name, description, and implementation according to your needs.
    """
    
    name: str = "Template Tool"
    description: str = """
    Generic template tool description.
    
    Key Features:
    - Feature 1
    - Feature 2
    - Feature 3
    
    Usage:
    Describe how to use the tool and its main capabilities.
    """
    
    args_schema: Type[BaseModel] = Field(default=TemplateToolRequest)

    def _run(self, **kwargs: Any) -> dict:
        """
        Execute the tool with validated parameters.
        
        Args:
            **kwargs: Keyword arguments matching TemplateToolRequest schema
        
        Returns:
            dict: Response containing success status and processed data
        """
        try:
            # Validate input parameters against schema
            params = self.args_schema(**kwargs)
            
            # Initialize response structure
            response = {
                'success': False,
                'data': None,
                'error': None
            }
            
            # TODO: Implement your tool logic here
            # Process the input parameters (params)
            # Perform the required operations
            # Update the response with results
            
            # Example processing
            processed_data = {
                'input_received': params.input_text,
                'max_results': params.max_results,
                'metadata_included': params.include_metadata
            }
            
            # Update response with success and data
            response.update({
                'success': True,
                'data': processed_data
            })
            
            return response

        except Exception as e:
            logger.error(f"Template tool error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }

    def _format_response(self, raw_data: Any) -> dict:
        """
        Format the raw data into a structured response.
        
        Args:
            raw_data: The raw data to format
            
        Returns:
            dict: Formatted response data
        """
        try:
            # TODO: Implement response formatting logic
            # Transform raw_data into desired format
            formatted_data = {
                'formatted_result': raw_data,
                'timestamp': None,  # Add timestamp if needed
                'metadata': {}  # Add any relevant metadata
            }
            
            return {
                'success': True,
                'data': formatted_data
            }
            
        except Exception as e:
            logger.error(f"Response formatting error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'data': None,
                'error': f"Failed to format response: {str(e)}"
            } 