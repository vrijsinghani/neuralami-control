import os
from typing import Any, Optional, Type, Dict
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
import logging
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from apps.file_manager.storage import PathManager
from distutils.util import strtobool

logger = logging.getLogger(__name__)


class FileWriterToolSchema(BaseModel):
    """Input schema for the FileWriterTool."""
    filename: str = Field(..., description="The name of the file to write to.")
    content: str = Field(..., description="The content to write to the file.")
    user_id: int = Field(..., description="The ID of the user making the request.")
    directory: Optional[str] = Field(None, description="Optional directory path within user's media directory.")
    overwrite: str = "False" # String type, default "False"


class FileWriterTool(BaseTool):
    name: str = "File Writer Tool"
    description: str = (
        "A tool to write content to a specified file within user's media directory. "
        "Accepts filename, content, and optionally a directory path and overwrite flag as input."
        "Returns a success message if the file is written successfully, otherwise returns an error message."
    )
    args_schema: Type[FileWriterToolSchema] = FileWriterToolSchema

    def _run(self, **kwargs: Any) -> str:
        logger.debug(f"FileWriterTool received RAW kwargs: {repr(kwargs)}") # Log RAW kwargs
        logger.debug(f"FileWriterTool received kwargs TYPE: {type(kwargs)}") # Log kwargs type
        logger.debug(f"FileWriterTool received kwargs KEYS: {kwargs.keys()}") # Log the keys
        try:
            filename = kwargs["filename"]
            content = kwargs["content"]
            user_id = kwargs["user_id"]
            directory = kwargs.get('directory', '/')  # Default to '/' if not provided
            
            # Handle cases where directory is explicitly 'None' as string
            if directory is None or directory == 'None':
                directory = '/'
                
            overwrite_str = kwargs["overwrite"]
            overwrite = bool(strtobool(overwrite_str))

            # Log the input parameters
            logger.debug(f"Writing file: {filename}, directory: {directory}, user_id: {user_id}, overwrite: {overwrite}")
            logger.debug(f"Content preview: {content[:100]}...")

            # Initialize PathManager with user_id
            path_manager = PathManager(user_id=user_id)

            # Construct the file path
            filepath = os.path.join(str(directory), str(filename)).lstrip('/')
            full_path = path_manager._get_full_path(filepath)

            logger.debug(f"Writing to path: {full_path}")

            # Check if file exists and overwrite is not allowed
            if default_storage.exists(full_path) and not overwrite:
                logger.error(f"File {filename} already exists and overwrite option was not passed.")
                return f"Error: File {filename} already exists and overwrite option was not passed."

            # Write content to the file using default_storage
            try:
                content_file = ContentFile(content.encode('utf-8'))
                if overwrite and default_storage.exists(full_path):
                    default_storage.delete(full_path)

                saved_path = default_storage.save(full_path, content_file)
                logger.debug(f"Successfully wrote content to {saved_path}")
                return f"SUCCESS: File '{filename}' written to {saved_path} (Length: {len(content)} chars)"

            except UnicodeEncodeError as ue:
                error_msg = f"Error encoding content: {str(ue)}"
                logger.error(error_msg)
                return f"ERROR: {error_msg}"

        except KeyError as ke:
            error_msg = f"Missing required key in input: {str(ke)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"An error occurred while writing to the file: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
