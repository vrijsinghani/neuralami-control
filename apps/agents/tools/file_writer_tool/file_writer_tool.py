import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging
from ..utils import get_safe_path

logger = logging.getLogger(__name__)


class FileWriterToolSchema(BaseModel):
    filename: str = Field(..., description="The name of the file to write to.")
    content: str = Field(..., description="The content to write to the file.")
    directory: Optional[str] = Field(None, description="Optional directory path within user's media directory.")
    overwrite: bool = Field(False, description="Whether to overwrite the file if it exists.")
    user_id: int = Field(..., description="The ID of the user making the request.")


class FileWriterTool(BaseTool):
    name: str = "File Writer Tool"
    description: str = (
        "A tool to write content to a specified file within user's media directory. "
        "Accepts filename, content, and optionally a directory path and overwrite flag as input."
    )
    args_schema: Type[BaseModel] = FileWriterToolSchema

    def _run(self, filename: str, content: str, user_id: int, directory: Optional[str] = None, overwrite: bool = False) -> str:
        try:
            # Get safe path within user's media directory
            filepath = get_safe_path(user_id, filename, directory)
            
            # Check if file exists and overwrite is not allowed
            if os.path.exists(filepath) and not overwrite:
                error_msg = f"File {filename} already exists and overwrite option was not passed."
                logger.error(error_msg)
                return error_msg

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Write content to the file
            mode = "w" if overwrite else "x"
            with open(filepath, mode) as file:
                file.write(content)
            logger.debug(f"Successfully wrote content to {filename}")
            return f"Content successfully written to {filename}"
        except ValueError as e:
            logger.error(str(e))
            return str(e)
        except Exception as e:
            error_msg = f"An error occurred while writing to the file: {str(e)}"
            logger.error(error_msg)
            return error_msg
