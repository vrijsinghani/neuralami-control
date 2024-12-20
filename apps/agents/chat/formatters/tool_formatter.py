import json
import logging
from typing import Any, Dict

from .table_formatter import TableFormatter

logger = logging.getLogger(__name__)

class ToolFormatter:
    """Handles formatting of tool outputs and usage messages"""
    
    @staticmethod
    def format_tool_output(content: Any) -> str:
        """Format tool output with proper styling"""
        try:
            if isinstance(content, dict):
                return f'<div class="json-output">{json.dumps(content, indent=2)}</div>'
            elif isinstance(content, str):
                # Try to parse as JSON first
                try:
                    json_content = json.loads(content)
                    return f'<div class="json-output">{json.dumps(json_content, indent=2)}</div>'
                except json.JSONDecodeError:
                    pass
                
                # Format as table if possible
                if TableFormatter.detect_tabular_data(content):
                    content = TableFormatter.format_table(content)
            
            return f'<div class="tool-output">{content}</div>'
        except Exception as e:
            logger.error(f"Error formatting tool output: {str(e)}")
            return str(content)

    @staticmethod
    def format_tool_usage(content: str, message_type: str = None) -> str:
        """Format tool usage messages"""
        if message_type == "tool_start" and content.startswith('Using tool:'):
            tool_info = content.split('\n')
            formatted = f'''
            <div class="tool-usage">
                <i class="fas fa-tools"></i>
                <div>
                    <strong>{tool_info[0]}</strong>
                    <div class="tool-input">{tool_info[1] if len(tool_info) > 1 else ''}</div>
                </div>
            </div>
            '''
            return formatted
        elif message_type == "tool_error":
            return f'''
            <div class="tool-error">
                <i class="fas fa-exclamation-triangle"></i>
                <div>{content}</div>
            </div>
            '''
        return content

    @staticmethod
    def format_tool_result(observation: Any) -> Dict:
        """Format tool output into a standardized structure"""
        try:
            result_data = {
                'tool_type': None,
                'format': None,
                'data': None,
                'metadata': {}
            }

            if isinstance(observation, dict):
                # Handle tabular data
                if TableFormatter.detect_tabular_data(observation):
                    result_data.update({
                        'tool_type': observation.get('type', 'generic'),
                        'format': 'table',
                        'data': TableFormatter.format_table(observation),
                        'metadata': {
                            'raw_data': observation.get('raw_data', {}),
                            'tool': observation.get('tool')
                        }
                    })
                
                # Handle validation errors
                elif observation.get('type') == 'error':
                    result_data.update({
                        'tool_type': 'error',
                        'format': 'error',
                        'data': {
                            'message': observation.get('message'),
                            'error_type': observation.get('error'),
                            'suggestion': observation.get('suggestion')
                        }
                    })
                
                # Handle other structured data
                else:
                    result_data.update({
                        'tool_type': observation.get('type', 'generic'),
                        'format': 'json',
                        'data': json.dumps(observation, indent=2),
                        'metadata': {
                            'tool': observation.get('tool')
                        }
                    })

            return result_data

        except Exception as e:
            logger.error(f"Error formatting tool result: {str(e)}", exc_info=True)
            return {
                'tool_type': 'error',
                'format': 'error',
                'data': {
                    'message': str(e),
                    'error_type': 'formatting_error'
                }
            } 