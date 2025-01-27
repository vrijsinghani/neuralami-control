import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging
from ..utils import get_safe_path

logger = logging.getLogger(__name__)


class DirectoryReadToolSchema(BaseModel):
    """Input for DirectoryReadTool."""
    directory: str = Field(..., description="Directory to list content within user's media directory")
    user_id: int = Field(..., description="The ID of the user making the request")


class DirectoryReadTool(BaseTool):
    name: str = "List files in directory"
    description: str = (
        "A tool that can be used to recursively list contents within user's media directory."
    )
    args_schema: Type[BaseModel] = DirectoryReadToolSchema

    def _run(self, directory: str, user_id: int) -> str:
        try:
            # Get safe path within user's media directory
            safe_directory = get_safe_path(user_id, directory)
            
            if not os.path.exists(safe_directory):
                return f"Directory {directory} does not exist"
                
            files_list = [
                os.path.relpath(os.path.join(root, name), safe_directory) + ('/' if os.path.isdir(os.path.join(root, name)) else ''
                for root, dirs, files in os.walk(safe_directory)
                for name in dirs + files
            ]
            
            if not files_list:
                return "No files or directories found in the specified location"
                
            files = "\n- ".join(files_list)
            logger.debug(f"Successfully listed files in directory: {directory}")
            return f"Directory contents:\n- {files}"
            
        except ValueError as e:
            logger.error(str(e))
            return str(e)
        except Exception as e:
            error_msg = f"An error occurred while listing directory: {str(e)}"
            logger.error(error_msg)
            return error_msg
