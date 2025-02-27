import importlib.util
import os
from typing import List, Optional, Type
import json
import logging
from django.conf import settings

import docker
from pydantic import BaseModel, Field

from crewai.tools import BaseTool

logger = logging.getLogger(__name__)


class CodeInterpreterSchema(BaseModel):
    """Input for CodeInterpreterTool."""
    code: str = Field(
        ...,
        description="Python3 code used to be interpreted in the Docker container. ALWAYS PRINT the final result and the output of the code",
    )

    libraries_used: List[str] = Field(
        ...,
        description="List of libraries used in the code with proper installing names separated by commas. Example: numpy,pandas,beautifulsoup4",
    )


class CodeInterpreterTool(BaseTool):
    name: str = "Code Interpreter"
    description: str = "Interprets Python3 code strings with a final print statement."
    args_schema: Type[BaseModel] = CodeInterpreterSchema
    default_image_tag: str = "code-interpreter:latest"
    code: Optional[str] = None
    user_dockerfile_path: Optional[str] = None

    @staticmethod
    def _get_installed_package_path():
        spec = importlib.util.find_spec("crewai_tools")
        return os.path.dirname(spec.origin)

    def _verify_docker_image(self) -> None:
        """
        Verify if the Docker image is available. Optionally use a user-provided Dockerfile.
        """
        client = docker.from_env()

        try:
            client.images.get(self.default_image_tag)

        except docker.errors.ImageNotFound:
            if self.user_dockerfile_path and os.path.exists(self.user_dockerfile_path):
                dockerfile_path = self.user_dockerfile_path
            else:
                package_path = self._get_installed_package_path()
                dockerfile_path = os.path.join(
                    package_path, "tools/code_interpreter_tool"
                )
                if not os.path.exists(dockerfile_path):
                    raise FileNotFoundError(
                        f"Dockerfile not found in {dockerfile_path}"
                    )

            client.images.build(
                path=dockerfile_path,
                tag=self.default_image_tag,
                rm=True,
            )

    def _run(self, code: str = None, libraries_used: List[str] = None) -> str:
        """Run code in Docker container with explicit parameters"""
        try:
            # Log raw input for debugging
            logger.debug(f"CodeInterpreterTool received: code={type(code)}, libraries={type(libraries_used)}")
            
            # Comprehensive input validation and normalization
            if code is None:
                return "Error: No code provided to execute"
            
            # Handle various input formats that might cause the ConverterError
            # Case 1: If code is a list, we need special handling
            if isinstance(code, list):
                if len(code) > 0:
                    first_item = code[0]
                    # Case 1a: List containing a dict with 'code' key
                    if isinstance(first_item, dict) and 'code' in first_item:
                        libraries_used = first_item.get('libraries_used', [])
                        code = first_item['code']
                    # Case 1b: List containing the code as a string
                    elif isinstance(first_item, str):
                        code = "\n".join(str(item) for item in code)
                    # Case 1c: Other list format - convert to string
                    else:
                        code = str(code)
            
            # Case 2: If code is a dict with 'code' key
            elif isinstance(code, dict) and 'code' in code:
                libraries_used = code.get('libraries_used', libraries_used or [])
                code = code['code']
            
            # Case 3: Ensure code is a string
            if not isinstance(code, str):
                code = str(code)
            
            # Case 4: Ensure libraries_used is a list of strings
            if libraries_used is None:
                libraries_used = []
            elif isinstance(libraries_used, str):
                libraries_used = [lib.strip() for lib in libraries_used.split(',') if lib.strip()]
            elif not isinstance(libraries_used, list):
                libraries_used = [str(libraries_used)]
            
            # Sanitize libraries to ensure they're all strings
            libraries_used = [str(lib) for lib in libraries_used]
            
            # Log the processed inputs
            logger.debug(f"Processed code (first 100 chars): {code[:100]}...")
            logger.debug(f"Processed libraries: {libraries_used}")
            
            # Execute the code in Docker
            return self.run_code_in_docker(code, libraries_used)
            
        except Exception as e:
            logger.error(f"Error in CodeInterpreterTool._run: {str(e)}", exc_info=True)
            return f"Error executing code: {str(e)}"

    def _install_libraries(
        self, container: docker.models.containers.Container, libraries: List[str]
    ) -> None:
        """
        Install missing libraries in the Docker container
        """
        for library in libraries:
            container.exec_run(f"pip install {library}")

    def _init_docker_container(self) -> docker.models.containers.Container:
        container_name = "code-interpreter"
        client = docker.from_env()
        current_path = os.getcwd()

        # Check if the container is already running
        try:
            existing_container = client.containers.get(container_name)
            existing_container.stop()
            existing_container.remove()
        except docker.errors.NotFound:
            pass  # Container does not exist, no need to remove

        return client.containers.run(
            self.default_image_tag,
            detach=True,
            tty=True,
            working_dir="/workspace",
            name=container_name,
            volumes={current_path: {"bind": "/workspace", "mode": "rw"}},  # type: ignore
        )

    def run_code_in_docker(self, code: str, libraries_used: List[str]) -> str:
        try:
            # Additional validation before running in Docker
            if not code or not isinstance(code, str):
                return "Error: Empty or invalid code provided"
                
            self._verify_docker_image()
            container = self._init_docker_container()
            
            # Install libraries with error handling
            for library in libraries_used:
                try:
                    logger.debug(f"Installing library: {library}")
                    result = container.exec_run(f"pip install {library}")
                    if result.exit_code != 0:
                        logger.warning(f"Failed to install library {library}: {result.output.decode('utf-8')}")
                except Exception as e:
                    logger.warning(f"Error installing library {library}: {str(e)}")
            
            # Escape code for proper execution in shell
            escaped_code = code.replace('"', '\\"').replace('$', '\\$')
            
            # Write code to a file instead of executing directly to avoid shell escaping issues
            file_path = "/tmp/code_to_execute.py"
            write_cmd = f'echo "{escaped_code}" > {file_path}'
            container.exec_run(write_cmd)
            
            # Execute the file instead of passing code directly
            cmd_to_run = f'python3 {file_path}'
            
            logger.debug(f"Executing code in container using file: {file_path}")
            exec_result = container.exec_run(cmd_to_run)
            
            # Clean up
            try:
                container.exec_run(f'rm {file_path}')
                container.stop()
                container.remove()
            except Exception as e:
                logger.warning(f"Error cleaning up container: {str(e)}")
            
            output = exec_result.output.decode("utf-8", errors="replace")
            if exec_result.exit_code != 0:
                logger.warning(f"Code execution failed with exit code {exec_result.exit_code}")
                return f"Something went wrong while running the code (exit code {exec_result.exit_code}): \n{output}"
            
            return output
        except Exception as e:
            logger.error(f"Error in run_code_in_docker: {str(e)}", exc_info=True)
            return f"Docker execution error: {str(e)}"
