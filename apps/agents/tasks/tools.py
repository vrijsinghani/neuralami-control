from celery import shared_task
import asyncio
import logging
from ..utils import load_tool
from django.shortcuts import get_object_or_404
from ..models import Tool, ToolRun
import inspect
import json
import traceback
from apps.organizations.utils import OrganizationContext

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_tool(self, tool_id: int, inputs: dict, organization_id: str):
    """Generic Celery task to run any tool"""
    try:
        # Load the tool
        tool = get_object_or_404(Tool, id=tool_id)
        tool_instance = load_tool(tool)
        
        if tool_instance is None:
            raise ValueError('Failed to load tool')

        # Create a tool run record
        tool_run = ToolRun.objects.create(
            tool=tool,
            status='STARTED',
            inputs=inputs
        )
        
        try:
            # Process inputs if tool has args_schema
            if hasattr(tool_instance, 'args_schema'):
                processed_inputs = {}
                for key, value in inputs.items():
                    if value != '':
                        try:
                            # Try to parse the string as JSON
                            parsed_value = json.loads(value)
                            processed_inputs[key] = parsed_value
                        except json.JSONDecodeError:
                            # If it's not valid JSON, use the raw value
                            processed_inputs[key] = value
                
                #logger.debug(f"Processed inputs before validation: {processed_inputs}")
                # Let Pydantic handle any type conversions
                validated_inputs = tool_instance.args_schema(**processed_inputs)
                inputs = validated_inputs.dict()
                
                # Get the signature of the _run method to only pass parameters it accepts
                sig = inspect.signature(tool_instance._run)
                # Filter inputs to only include parameters accepted by the _run method
                filtered_inputs = {}
                for param_name in sig.parameters:
                    if param_name in inputs:
                        filtered_inputs[param_name] = inputs[param_name]
                    
                #logger.debug(f"Filtered inputs to match method signature: {filtered_inputs}")
                inputs = filtered_inputs
            
            # Set organization context before running the tool
            with OrganizationContext.organization_context(organization_id):
                # logger.debug(f"Organization context set to: {organization_id}") # Removed log
                # Run the tool
                if inspect.iscoroutinefunction(tool_instance._run):
                    # Create event loop for async tools
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(tool_instance._run(**inputs))
                    finally:
                        loop.close()
                else:
                    result = tool_instance._run(**inputs)
            
            # Update tool run record
            tool_run.status = 'SUCCESS'
            tool_run.result = result
            tool_run.save()
            
            return {
                'result': result,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error running tool: {str(e)}\n{traceback.format_exc()}")
            tool_run.status = 'FAILURE'
            tool_run.error = str(e)
            tool_run.save()
            raise
            
    except Exception as e:
        logger.error(f"Error in run_tool task: {str(e)}\n{traceback.format_exc()}")
        raise
