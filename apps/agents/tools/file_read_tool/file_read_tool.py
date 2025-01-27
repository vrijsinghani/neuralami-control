from typing import Any, Type
from pydantic import BaseModel, Field
from langchain.schema import StrOutputParser
from crewai.tools import BaseTool
import logging
from django.conf import settings
from ..utils import get_safe_path

logger = logging.getLogger(__name__)

class FileReadToolSchema(BaseModel):
    """Input schema for FileReadTool."""
    file_path: str = Field(..., description="File path within user's media directory")
    user_id: int = Field(..., description="The ID of the user making the request")

class FileReadTool(BaseTool):
    name: str = "File Read Tool"
    description: str = "A tool that can be used to read a file's content within user's media directory."
    args_schema: Type[BaseModel] = FileReadToolSchema

    def _run(self, file_path: str, user_id: int) -> str:
        try:
            # Get safe path within user's media directory
            safe_path = get_safe_path(user_id, file_path)
            
            with open(safe_path, "r") as file:
                content = file.read()
            logger.debug(f"Successfully read file: {file_path}")
            return content
            
        except ValueError as e:
            logger.error(str(e))
            return str(e)
        except Exception as e:
            error_msg = f"Failed to read the file {file_path}. Error: {str(e)}"
            logger.error(error_msg)
            return error_msg
