from functools import wraps
import logging
import json
from typing import Optional, Any, Callable
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class ChatError(Exception):
    """Base class for chat-related errors"""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code

def handle_chat_errors(func: Callable) -> Callable:
    """Decorator to handle chat-related errors"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ChatError as e:
            logger.warning(f"Chat error: {str(e)}", exc_info=True)
            return {
                'error': True,
                'message': str(e),
                'code': e.code
            }
        except ValidationError as e:
            logger.warning(f"Validation error: {str(e)}", exc_info=True)
            return {
                'error': True,
                'message': str(e),
                'code': 'validation_error'
            }
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return {
                'error': True,
                'message': 'An unexpected error occurred',
                'code': 'internal_error'
            }
    return wrapper 