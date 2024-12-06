from celery import shared_task
import asyncio
import logging
from .utils import load_tool
from django.shortcuts import get_object_or_404
from .models import Tool, ToolRun
import inspect
import json
import traceback

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_tool(self, tool_id: int, inputs: dict):
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
            status='running',
            inputs=inputs
        )
        
        try:
            # Process inputs if tool has args_schema
            if hasattr(tool_instance, 'args_schema'):
                processed_inputs = {}
                for key, value in inputs.items():
                    if value != '':
                        try:
                            processed_inputs[key] = json.loads(value)
                        except json.JSONDecodeError:
                            processed_inputs[key] = value
                            
                validated_inputs = tool_instance.args_schema(**processed_inputs)
                inputs = validated_inputs.dict()
            
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
                # Run sync tools directly
                result = tool_instance._run(**inputs)
            
            # Update tool run record with success
            tool_run.status = 'completed'
            tool_run.result = result
            tool_run.save()
            
            return {
                'status': 'completed',
                'result': result,
                'tool_run_id': tool_run.id
            }
            
        except Exception as e:
            # Update tool run record with error
            tool_run.status = 'failed'
            tool_run.error = str(e)
            tool_run.save()
            raise
            
    except Exception as e:
        logger.error(f"Error running tool: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'failed',
            'error': str(e)
        }
