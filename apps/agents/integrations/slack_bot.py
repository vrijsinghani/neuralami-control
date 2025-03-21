import logging
import json
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async
from slack_sdk import WebClient
import threading
import time
from django.conf import settings
from django.db import connections
from django.db.models import Model
import uuid
import hashlib
from typing import Dict, Any, Union, List, Optional
from langchain_core.agents import AgentFinish
from .slack_message_formatter import SlackMessageFormatter
from django.conf import settings
from apps.agents.websockets.services.chat_service import AgentChatService


logger = logging.getLogger(__name__)

_slack_client = None

def get_client_for_channel(channel_id, team_id=None):
    """Get the client ID for a given Slack channel"""
    from apps.agents.models import SlackChannelClientMapping
    try:
        mapping = SlackChannelClientMapping.objects.get(channel_id=channel_id)
        return mapping.client_id
    except SlackChannelClientMapping.DoesNotExist:
        logger.warning(f"No client mapping found for channel {channel_id}")
        return None

def get_django_user_from_slack(user_id, team_id):
    """Get Django user from Slack user ID and team ID"""
    from apps.agents.models import UserSlackIntegration
    try:
        # Get the Slack integration for this team
        integration = UserSlackIntegration.objects.get(team_id=team_id, is_active=True)
        
        # Verify this is the correct user using Slack API
        client = WebClient(token=integration.access_token)
        user_info = client.users_info(user=user_id)
        
        if user_info['ok']:
            return integration.user
        
    except Exception as e:
        logger.error(f"Error getting Django user from Slack: {e}")
    
    return None

class SlackWebSocketClient:
    """Client for handling Slack WebSocket connections."""

    def __init__(self, channel_id, thread_ts, user_id, client_id=None):
        """Initialize the client."""
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.user_id = user_id
        self.client_id = client_id
        
        # Create a deterministic UUID from channel and thread
        hash_input = f"slack_{channel_id}_{thread_ts}".encode('utf-8')
        hash_hex = hashlib.md5(hash_input).hexdigest()
        self.session_id = str(uuid.UUID(hash_hex))
        
        self.websocket = None
        self.say_callback = None
        self.web_client = WebClient(token=settings.DSLACK_BOT_TOKEN)

    async def connect(self, say_callback):
        """Connect to chat service WebSocket"""
        try:
            self.say_callback = say_callback
            
            # Import here to avoid circular imports
            from apps.agents.websockets.services.chat_service import ChatService
            from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler
            from apps.agents.models import Agent
            
            # Get default agent
            agent = await sync_to_async(Agent.objects.get)(id=25)  # TODO: Make configurable
            
            # Create custom callback handler for Slack
            class SlackCallbackHandler(WebSocketCallbackHandler):
                def __init__(self, slack_client, message_formatter, channel_id):
                    super().__init__(slack_client)
                    self.slack_client = slack_client
                    self.message_formatter = message_formatter
                    self.channel_id = channel_id

                async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
                    """Handle tool start - send tool name and input."""
                    try:
                        # Skip internal exceptions
                        if serialized.get('name') == '_Exception':
                            return

                        tool_name = serialized.get('name', 'Unknown Tool')
                        self.slack_client.say_callback(
                            channel=self.channel_id,
                            thread_ts=self.slack_client.thread_ts,
                            blocks=[{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"🔧 Using tool: *{tool_name}*"
                                }
                            }, {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"```{input_str}```"
                                }
                            }],
                            text="Tool started"
                        )
                        
                        # Track token usage if available
                        token_usage = kwargs.get('token_usage', {})
                        if self.token_manager:
                            self.token_manager.track_token_usage(
                                token_usage.get('prompt_tokens', 0),
                                token_usage.get('completion_tokens', 0)
                            )
                    except Exception as e:
                        logger.error(f"Error in on_tool_start: {str(e)}", exc_info=True)

                async def on_tool_end(self, tool_result: Any, tool_name: str = None, **kwargs):
                    """Handle tool completion by sending the result to Slack."""
                    try:
                        # Handle the result more safely
                        if isinstance(tool_result, str):
                            try:
                                result = json.loads(tool_result)
                            except json.JSONDecodeError:
                                # If it's not JSON, use the string directly
                                result = {"text": tool_result}
                        else:
                            result = tool_result
                        
                        # Format the result for Slack
                        formatted_result = self.message_formatter.format_tool_result(result)
                        
                        # If formatted result is a list of blocks
                        if isinstance(formatted_result, list):
                            # Check if we have an image block
                            image_blocks = [b for b in formatted_result if b.get('type') == 'image']
                            non_image_blocks = [b for b in formatted_result if b.get('type') != 'image']
                            
                            if image_blocks:
                                # First send non-image blocks
                                if non_image_blocks:
                                    self.slack_client.say_callback(
                                        channel=self.channel_id,
                                        thread_ts=self.slack_client.thread_ts,
                                        blocks=non_image_blocks[:50],  # Slack limit
                                        text="Tool result"
                                    )
                                
                                try:
                                    # Get time series info first
                                    time_series_info = self.message_formatter._find_time_series_data(result)
                                    if time_series_info:
                                        date_fields, metric_fields = time_series_info
                                        if date_fields and metric_fields:
                                            # Extract the data we need
                                            table_data = self.message_formatter._find_table_data(result)
                                            if table_data:
                                                # Create and upload chart
                                                chart_bytes = self.message_formatter._create_chart(
                                                    table_data,
                                                    date_fields[0],
                                                    metric_fields
                                                )
                                                
                                                # Upload file
                                                self.slack_client.files_upload_v2(
                                                    channel=self.channel_id,
                                                    thread_ts=self.slack_client.thread_ts,
                                                    file=chart_bytes,
                                                    filename="chart.png",
                                                    title="Time Series Chart"
                                                )
                                except Exception as e:
                                    logger.error(f"Error creating/uploading chart: {str(e)}", exc_info=True)
                                    # Continue without the chart
                            else:
                                # Send all blocks if no image
                                self.slack_client.say_callback(
                                    channel=self.channel_id,
                                    thread_ts=self.slack_client.thread_ts,
                                    blocks=formatted_result[:50],  # Slack limit
                                    text="Tool result"
                                )
                        else:
                            # If it's just text, send it directly
                            self.slack_client.say_callback(
                                channel=self.channel_id,
                                thread_ts=self.slack_client.thread_ts,
                                text=formatted_result
                            )
                            
                    except Exception as e:
                        logger.error(f"Error in on_tool_end: {str(e)}", exc_info=True)
                        self.slack_client.say_callback(
                            channel=self.channel_id,
                            thread_ts=self.slack_client.thread_ts,
                            text=f"Error processing tool result: {str(e)}"
                        )

                async def on_tool_error(self, error: str, **kwargs: Any):
                    """Handle tool errors"""
                    try:
                        self.slack_client.say_callback(
                            channel=self.channel_id,
                            thread_ts=self.slack_client.thread_ts,
                            blocks=[{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"❌ Tool error: {error}"
                                }
                            }],
                            text="Tool error"
                        )
                        
                        # Track token usage if available
                        token_usage = kwargs.get('token_usage', {})
                        if self.token_manager:
                            self.token_manager.track_token_usage(
                                token_usage.get('prompt_tokens', 0),
                                token_usage.get('completion_tokens', 0)
                            )
                    except Exception as e:
                        logger.error(f"Error in on_tool_error: {str(e)}", exc_info=True)

                async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any):
                    """Handle agent completion - send final answer."""
                    try:
                        if hasattr(finish, 'return_values'):
                            output = finish.return_values.get('output', '')
                            if output.strip():
                                self.slack_client.say_callback(
                                    channel=self.channel_id,
                                    thread_ts=self.slack_client.thread_ts,
                                    blocks=[{
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": output
                                        }
                                    }],
                                    text="Agent finished"
                                )
                            
                            # Track token usage if available
                            token_usage = kwargs.get('token_usage', {})
                            if self.token_manager:
                                self.token_manager.track_token_usage(
                                    token_usage.get('prompt_tokens', 0),
                                    token_usage.get('completion_tokens', 0)
                                )
                                await self.token_manager.track_conversation_tokens()
                    except Exception as e:
                        logger.error(f"Error in on_agent_finish: {str(e)}", exc_info=True)
            
            # Initialize chat service with custom handler
            callback_handler = SlackCallbackHandler(
                slack_client=self,
                message_formatter=SlackMessageFormatter(),
                channel_id=self.channel_id
            )
            
            # Initialize chat service
            self.chat_service = AgentChatService(
                agent=agent,
                model_name=settings.GENERAL_MODEL,  # TODO: Make configurable
                client_data={'client_id': self.client_id, 'user_id': self.user_id},
                callback_handler=callback_handler,
                session_id=self.session_id
            )
            
            # Initialize the service
            await self.chat_service.initialize()
            
            logger.info(f"Connected WebSocket for channel {self.channel_id}")
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}", exc_info=True)
            raise

    async def send_json(self, content):
        """Callback handler uses this to send messages back to Slack"""
        if self.say_callback:
            message = content.get('message', '')
            if message:
                await sync_to_async(self.say_callback)(
                    text=message,
                    thread_ts=self.thread_ts
                )

    async def send_message(self, message):
        """Send message to chat service"""
        try:
            if not self.chat_service:
                raise Exception("WebSocket not connected")
                
            # Process message through chat service
            await self.chat_service.process_message(message)
            
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            if self.say_callback:
                await sync_to_async(self.say_callback)(
                    text=f"Error processing message: {str(e)}",
                    thread_ts=self.thread_ts
                )

    def say_callback(self, **kwargs):
        """Send a message to Slack."""
        return self.web_client.chat_postMessage(**kwargs)

    def files_upload_v2(self, **kwargs):
        """Upload a file to Slack using v2 API."""
        return self.web_client.files_upload_v2(**kwargs)

def process_message(message, say, is_mention=False):
    """Process a Slack message and send to chat service"""
    try:
        # Extract message details
        channel_id = message["channel"]
        user_id = message["user"]
        team_id = message.get("team")  # Get team ID from message
        text = message["text"]
        
        # Get Django user
        django_user = get_django_user_from_slack(user_id, team_id)
        if not django_user:
            logger.error(f"No Django user found for Slack user {user_id} in team {team_id}")
            say(
                text="Sorry, I couldn't find your user account. Please make sure you've connected your Slack account.",
                thread_ts=message.get('thread_ts', message.get('ts'))
            )
            return
        
        # For mentions, remove the bot mention
        if is_mention:
            text = text.split(">", 1)[1].strip()
            logger.info(f"Extracted text from mention: {text}")
        else:
            logger.info(f"Processing regular message: {text}")
        
        # Get thread_ts
        thread_ts = message.get('thread_ts', message.get('ts'))
        
        # Get client ID
        client_id = get_client_for_channel(channel_id)
        logger.info(f"Using client_id: {client_id} for channel: {channel_id}")

        # Send acknowledgment right away
        say(
            text="Processing your request...",
            thread_ts=thread_ts
        )
        
        # Create WebSocket client
        client = SlackWebSocketClient(
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_id=django_user.id,  # Use Django user ID instead of Slack user ID
            client_id=client_id
        )
        
        # Create event loop for async operations
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run async operations
        async def process():
            try:
                await client.connect(say)
                await client.send_message(text)
            except Exception as e:
                logger.error(f"Error in async processing: {e}", exc_info=True)
                await sync_to_async(say)(
                    text=f"Error processing message: {str(e)}",
                    thread_ts=thread_ts
                )
                
        # Run the async process in the event loop
        loop.run_until_complete(process())
        loop.close()
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        say(
            text=f"Sorry, I encountered an error: {str(e)}",
            thread_ts=message.get('thread_ts', message.get('ts'))
        )

def maintain_connection():
    """Keep the Slack connection alive and handle reconnections"""
    global _slack_client
    while True:
        try:
            if _slack_client and not _slack_client.is_connected():
                logger.warning("Slack connection lost, attempting to reconnect...")
                _slack_client.connect()
                if _slack_client.is_connected():
                    logger.info("Successfully reconnected to Slack")
                else:
                    logger.error("Failed to reconnect to Slack")
        except Exception as e:
            logger.error(f"Error in connection maintenance: {e}")
        time.sleep(60)  # Check connection every minute

def start_slack_bot():
    """Start the Slack bot in Socket Mode"""
    try:
        # Get tokens
        bot_token = settings.DSLACK_BOT_TOKEN
        app_token = settings.DSLACK_APP_TOKEN
        
        if not bot_token or not app_token:
            logger.warning("Slack tokens not found, skipping bot initialization")
            return
        
        # Initialize app with bot token
        app = App(token=bot_token)
        
        # Listen for messages (not mentions)
        @app.message("")
        def handle_message(message, say):
            logger.info(f"Received message: {message}")
            # Ignore bot messages
            if message.get("bot_id") or message.get("subtype") == "bot_message":
                logger.info("Ignoring bot message")
                return
            process_message(message, say)
        
        # Listen for mentions
        @app.event("app_mention")
        def handle_mention(event, say):
            logger.info(f"Received mention: {event}")
            process_message(event, say, is_mention=True)
        
        # Start socket mode handler in a thread
        def run_handler():
            try:
                handler = SocketModeHandler(app, app_token)
                handler.start()
            except Exception as e:
                logger.error(f"Error in socket handler: {e}", exc_info=True)
        
        socket_thread = threading.Thread(target=run_handler)
        socket_thread.daemon = True
        socket_thread.start()
        
    except Exception as e:
        logger.error(f"Error starting Slack bot: {str(e)}", exc_info=True)