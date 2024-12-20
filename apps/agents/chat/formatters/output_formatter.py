import json
import logging
from typing import Any, Dict

from .table_formatter import TableFormatter

logger = logging.getLogger(__name__)

class OutputFormatter:
    """Handles general output formatting"""
    
    @staticmethod
    def format_response(response: Dict) -> str:
        """Format agent response"""
        try:
            output = response.get("output")
            if not output:
                return "No response generated"
                
            # If output is a dict, check for tabular data
            if isinstance(output, dict):
                if "formatted_table" in output:
                    return output["formatted_table"]
                if TableFormatter.detect_tabular_data(output):
                    return TableFormatter.format_table(output)
                return json.dumps(output, indent=2)
                
            # If output is a string but contains JSON, try to parse and format
            if isinstance(output, str) and (output.startswith('{') or output.startswith('[')):
                try:
                    json_data = json.loads(output)
                    if "formatted_table" in json_data:
                        return json_data["formatted_table"]
                    if TableFormatter.detect_tabular_data(json_data):
                        return TableFormatter.format_table(json_data)
                    return json.dumps(json_data, indent=2)
                except json.JSONDecodeError:
                    pass
                    
            return output

        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}", exc_info=True)
            return "Error formatting response"

    @staticmethod
    def format_final_answer(content: Any) -> str:
        """Format the final agent response"""
        try:
            # Format as table if possible
            if TableFormatter.detect_tabular_data(content):
                content = TableFormatter.format_table(content)
            return f'<div class="agent-response">{content}</div>'
        except Exception as e:
            logger.error(f"Error formatting final answer: {str(e)}")
            return str(content) 