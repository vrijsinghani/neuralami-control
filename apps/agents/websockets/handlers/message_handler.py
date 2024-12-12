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
        """Format tool output for display"""
        try:
            logger.debug(f"Formatting tool output. Raw content: {content}")
            
            # Handle tool execution results
            if isinstance(content, dict):
                if 'type' in content and content['type'] == 'tool_execution':
                    formatted = {
                        'tool': content.get('name'),
                        'input': content.get('input'),
                        'output': content.get('output')
                    }
                    return json.dumps(formatted, indent=2)
                    
                if 'agent' in content and 'messages' in content['agent']:
                    logger.debug("Processing agent messages structure")
                    messages = content['agent']['messages']
                    formatted_messages = []
                    for msg in messages:
                        logger.debug(f"Processing message: {msg}")
                        if hasattr(msg, 'content'):
                            formatted_messages.append(msg.content)
                    return json.dumps(formatted_messages, indent=2)

            # If content is a string, try to parse as JSON first
            if isinstance(content, str):
                try:
                    # Check for duplicated JSON blocks
                    if content.count('```json') > 1:
                        logger.warning(f"Multiple JSON blocks detected in: {content}")
                        # Take only the first JSON block
                        json_blocks = content.split('```json')
                        content = json_blocks[1].split('```')[0]
                        
                    json_content = json.loads(content)
                    logger.debug(f"Parsed JSON content: {json_content}")
                    return json.dumps(json_content, indent=2)
                except json.JSONDecodeError as e:
                    logger.debug(f"Not JSON content, using as is: {content}")
                    return content

            # Handle nested message structures
            if isinstance(content, dict):
                # Handle tool messages structure
                if 'tools' in content and 'messages' in content['tools']:
                    messages = content['tools']['messages']
                    # Extract content from ToolMessage objects
                    formatted_messages = []
                    for msg in messages:
                        if hasattr(msg, 'content'):
                            try:
                                # Try to parse content as JSON
                                msg_content = json.loads(msg.content)
                                formatted_messages.append(msg_content)
                            except json.JSONDecodeError:
                                formatted_messages.append(msg.content)
                        else:
                            formatted_messages.append(str(msg))
                    return json.dumps(formatted_messages, indent=2)

                # Default dict handling
                return json.dumps(content, indent=2)

            # Check for table format
            if isinstance(content, str):
                if '|' in content and '-|-' in content:
                    return self.format_table(content)

                # Check for list format
                if content.strip().startswith(('-', '*', '1.')) or '\n-' in content or '\n*' in content:
                    return content

            # Default formatting
            return str(content)
            
        except Exception as e:
            logger.error(f"Error formatting tool output: {str(e)}", exc_info=True)
            return str(content)

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

                # Check for tool messages
                if isinstance(message, str):
                    if message.startswith('AgentAction:') or message.startswith('AgentStep:'):
                        response_data = {
                            'type': 'agent_message',
                            'message': message,
                            'is_agent': True,
                            'error': False,
                            'is_stream': False,
                            'message_type': 'tool',
                            'timestamp': datetime.now().isoformat()
                        }
                        logger.debug(f"📤 Sending tool message")
                        await self.consumer.send_json(response_data)
                        return

                # Apply formatting based on message type
                if message_type == "tool_output":
                    content = self.format_tool_output(content)
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