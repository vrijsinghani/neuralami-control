import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from apps.file_manager.storage import PathManager

logger = logging.getLogger(__name__)


class FileWriterToolSchema(BaseModel):
    filename: str = Field(..., description="The name of the file to write to.")
    content: str = Field(..., description="The content to write to the file.")
    user_id: int = Field(..., description="The ID of the user making the request.")
    directory: Optional[str] = Field(None, description="Optional directory path within user's media directory.")
    overwrite: bool = Field(False, description="Whether to overwrite the file if it exists.")


class FileWriterTool(BaseTool):
    name: str = "File Writer Tool"
    description: str = (
        "A tool to write content to a specified file within user's media directory. "
        "Accepts filename, content, and optionally a directory path and overwrite flag as input."
    )
    args_schema: Type[BaseModel] = FileWriterToolSchema

    def _run(self, filename: str, content: str, user_id: int, directory: Optional[str] = None, overwrite: bool = False) -> str:
        try:
            # Initialize PathManager with user_id
            path_manager = PathManager(user_id=user_id)
            logger.debug("writing file with file_writer")
            # Construct the file path
            filepath = os.path.join(directory, filename).lstrip('/') if directory else filename
            full_path = path_manager._get_full_path(filepath)
            
            logger.debug(f"Writing to path: {full_path}")
            
            # Check if file exists and overwrite is not allowed
            if default_storage.exists(full_path) and not overwrite:
                error_msg = f"File {filename} already exists and overwrite option was not passed."
                logger.error(error_msg)
                return error_msg

            # Write content to the file using default_storage
            content_file = ContentFile(content.encode('utf-8'))
            if overwrite:
                # Delete existing file if overwriting
                if default_storage.exists(full_path):
                    default_storage.delete(full_path)
            
            saved_path = default_storage.save(full_path, content_file)
            logger.debug(f"Successfully wrote content to {saved_path}")
            return f"Content successfully written to {filename}"
            
        except Exception as e:
            error_msg = f"An error occurred while writing to the file: {str(e)}"
            logger.error(error_msg)
            return error_msg
