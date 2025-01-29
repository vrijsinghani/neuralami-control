import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging
from apps.file_manager.storage import PathManager

logger = logging.getLogger(__name__)


class DirectoryReadToolSchema(BaseModel):
    """Input for DirectoryReadTool."""
    directory: str = Field(default="/", description="Directory to list content within user's media directory")
    user_id: int = Field(..., description="The ID of the user making the request")


class DirectoryReadTool(BaseTool):
    name: str = "List files in directory"
    description: str = (
        "A tool that can be used to list contents within user's media directory."
    )
    args_schema: Type[BaseModel] = DirectoryReadToolSchema

    def _run(self, directory: str, user_id: int) -> str:
        try:
            path_manager = PathManager(user_id=user_id)
            
            # Get directory contents using storage system
            contents = path_manager.list_contents(directory)
            
            if not contents:
                return f"No files or directories found in {directory}"
            
            # Format directory listing
            formatted = []
            for item in contents:
                entry = f"{item['path']}/" if item['type'] == 'directory' else item['path']
                formatted.append(entry)
            
            return "Directory contents:\n- " + "\n- ".join(sorted(formatted))
            
        except Exception as e:
            error_msg = f"Error listing directory: {str(e)}"
            logger.error(error_msg)
            return error_msg
