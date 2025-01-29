from typing import Any, Type
from pydantic import BaseModel, Field
from langchain.schema import StrOutputParser
from crewai.tools import BaseTool
import logging
from django.conf import settings
from django.core.files.storage import default_storage
from apps.file_manager.storage import PathManager

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
            # Initialize PathManager with user_id
            path_manager = PathManager(user_id=user_id)
            logger.debug("reading file with file_reader")
            
            # Get full path using PathManager
            full_path = path_manager._get_full_path(file_path)
            logger.debug(f"Reading from path: {full_path}")
            
            # Check if file exists
            if not default_storage.exists(full_path):
                error_msg = f"File {file_path} does not exist"
                logger.error(error_msg)
                return error_msg
            
            # Read content using default_storage
            with default_storage.open(full_path, 'r') as file:
                content = file.read()
                
            logger.debug(f"Successfully read file: {file_path}")
            return content
            
        except Exception as e:
            error_msg = f"Failed to read the file {file_path}. Error: {str(e)}"
            logger.error(error_msg)
            return error_msg
