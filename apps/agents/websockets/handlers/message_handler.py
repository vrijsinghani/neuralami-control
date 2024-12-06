import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, consumer):
        self.consumer = consumer

    def format_table(self, content):
        """Format content as an HTML table if it contains tabular data"""
        try:
            # Check if content has table-like format (e.g., "Date | Users")
            if '|' in content and '-|-' in content:
                lines = [line.strip() for line in content.strip().split('\n')]
                
                # Find the header line
                header_line = None
                separator_line = None
                data_lines = []
                
                for i, line in enumerate(lines):
                    if '|' in line:
                        if header_line is None:
                            header_line = line
                        elif separator_line is None and '-|-' in line:
                            separator_line = line
                        else:
                            data_lines.append(line)
                
                if not header_line or not separator_line:
                    return content
                    
                # Process headers
                headers = [h.strip() for h in header_line.split('|') if h.strip()]
                
                # Create HTML table
                html = ['<table class="table"><thead><tr>']
                html.extend([f'<th>{h}</th>' for h in headers])
                html.append('</tr></thead><tbody>')
                
                # Process data rows
                for line in data_lines:
                    if '|' in line:
                        cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                        if cells:
                            html.append('<tr>')
                            html.extend([f'<td>{cell}</td>' for cell in cells])
                            html.append('</tr>')
                
                html.append('</tbody></table>')
                return '\n'.join(html)
                
            return content
            
        except Exception as e:
            logger.error(f"Error formatting table: {str(e)}")
            return content

    def format_tool_output(self, content):
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
                content = self.format_table(content)
            
            return f'<div class="tool-output">{content}</div>'
        except Exception as e:
            logger.error(f"Error formatting tool output: {str(e)}")
            return content

    def format_tool_usage(self, content, message_type=None):
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

    def format_final_answer(self, content):
        """Format the final agent response"""
        try:
            # Format as table if possible
            content = self.format_table(content)
            return f'<div class="agent-response">{content}</div>'
        except Exception as e:
            logger.error(f"Error formatting final answer: {str(e)}")
            return content

    async def handle_message(self, message, is_agent=True, error=False, is_stream=False, message_type=None):
        """Format and send a message"""
        try:
            content = str(message)
            
            if is_agent:
                # Handle invalid/incomplete response errors
                if isinstance(message, dict) and 'steps' in message:
                    step = message['steps'][0]
                    if step.action.tool == '_Exception' and 'Could not parse LLM output' in step.log:
                        logger.warning(f"LLM parsing error: {step.log}")
                        error = True
                        content = "I encountered an error processing your request. Let me try again with a simpler query."

                # Apply formatting based on message type
                if message_type == "tool_output":
                    content = self.format_tool_output(content)
                elif message_type in ["tool_start", "tool_error"]:
                    content = self.format_tool_usage(content, message_type)
                elif message_type == "final_answer":
                    content = self.format_final_answer(content)
                else:
                    # Default formatting for other types
                    content = self.format_table(content)
            
            response_data = {
                'type': 'agent_message' if is_agent else 'user_message',
                'message': content,
                'is_agent': bool(is_agent),
                'error': bool(error),
                'is_stream': bool(is_stream),
                'message_type': message_type,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.debug(f"📤 Sending {'agent' if is_agent else 'user'} message type: {message_type}")
            
            await self.consumer.send_json(response_data)
            
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            await self.consumer.send_json({
                'type': 'error',
                'error': True,
                'message': 'Error processing message'
            })

    async def handle_keep_alive(self):
        """Handle keep-alive messages"""
        await self.consumer.send_json({
            'type': 'keep_alive_response',
            'timestamp': datetime.now().isoformat()
        }) 