import os
from typing import Any, Type, Set, Dict, Optional, List
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
import dotenv
import json

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

class AgentSchema(BaseModel):
    """Schema for Agent operations"""
    name: str = Field(..., description="Name of the agent")
    role: str = Field(..., description="Role of the agent")
    goal: str = Field(..., description="Goal of the agent")
    backstory: str = Field(..., description="Backstory of the agent")
    llm: Optional[str] = Field(None, description="LLM model to use")
    verbose: Optional[bool] = Field(False, description="Enable verbose mode")

class TaskSchema(BaseModel):
    """Schema for Task operations"""
    description: str = Field(..., description="Description of the task")
    agent_id: Optional[int] = Field(None, description="ID of the agent assigned to this task")
    expected_output: str = Field(..., description="Expected output of the task")
    async_execution: Optional[bool] = Field(False, description="Enable async execution")

class CrewSchema(BaseModel):
    """Schema for Crew operations"""
    name: str = Field(..., description="Name of the crew")
    agent_ids: List[int] = Field(..., description="List of agent IDs in the crew")
    process: str = Field("sequential", description="Process type: 'sequential' or 'hierarchical'")
    verbose: Optional[bool] = Field(False, description="Enable verbose mode")

class ToolSchema(BaseModel):
    """Schema for Tool operations"""
    tool_class: str = Field(..., description="Class of the tool")
    tool_subclass: str = Field(..., description="Subclass of the tool")
    name: str = Field(..., description="Name of the tool")
    description: str = Field("", description="Description of the tool")
    module_path: str = Field(..., description="Module path of the tool")

class NeuralAMIAPISchema(BaseModel):
    """Input schema for NeuralAMI API Tool"""
    operation: str = Field(
        ...,
        description="Operation to perform: list_agents, get_agent, create_agent, update_agent, delete_agent, "
                   "list_tasks, get_task, create_task, update_task, delete_task, "
                   "list_crews, get_crew, create_crew, update_crew, delete_crew"
                   "list_tools, get_tool, create_tool, update_tool, delete_tool"

    )
    resource_id: Optional[int] = Field(None, description="ID of the resource for get/update/delete operations")
    data: Optional[dict] = Field(None, description="Data for create/update operations")

class NeuralAMIAPITool(BaseTool):
    name: str = "NeuralAMI API Tool"
    description: str = "A tool for interacting with NeuralAMI API to manage agents, tasks, tools, and crews"
    args_schema: Type[BaseModel] = NeuralAMIAPISchema
    tags: Set[str] = {"api", "agents", "tasks", "crews", "management"}

    # Add these as Pydantic fields
    base_url: str = Field(
        default_factory=lambda: os.getenv('CSRF_TRUSTED_ORIGINS', 'https://manager.neuralami.com').rstrip('/'),
        description="Base URL for the API"
    )
    api_token: str = Field(
        default_factory=lambda: os.getenv('NEURALAMI_API_TOKEN'),
        description="API token for authentication"
    )

    def __init__(self, **data):
        super().__init__(**data)
        if not self.api_token:
            logger.error("NEURALAMI_API_TOKEN is not set in environment variables")
            raise ValueError("NEURALAMI_API_TOKEN is required")

    def _get_headers(self):
        """Get headers for API requests"""
        return {
            'Authorization': f'Token {self.api_token}',
            'Content-Type': 'application/json'
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def _make_request(self, method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
        """Make API request with retry mechanism"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = self._get_headers()

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data if data else None
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response content: {e.response.text[:500]}...")
            raise

    def _run(
        self,
        operation: str,
        resource_id: Optional[int] = None,
        data: Optional[dict] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute the API operation"""

        # Map operations to HTTP methods and endpoints
        operation_map = {
            # Agent operations
            'list_agents': ('GET', 'agents/'),
            'get_agent': ('GET', f'agents/{resource_id}/'),
            'create_agent': ('POST', 'agents/'),
            'update_agent': ('PUT', f'agents/{resource_id}/'),
            'delete_agent': ('DELETE', f'agents/{resource_id}/'),

            # Task operations
            'list_tasks': ('GET', 'tasks/'),
            'get_task': ('GET', f'tasks/{resource_id}/'),
            'create_task': ('POST', 'tasks/'),
            'update_task': ('PUT', f'tasks/{resource_id}/'),
            'delete_task': ('DELETE', f'tasks/{resource_id}/'),

            # Crew operations
            'list_crews': ('GET', 'crews/'),
            'get_crew': ('GET', f'crews/{resource_id}/'),
            'create_crew': ('POST', 'crews/'),
            'update_crew': ('PUT', f'crews/{resource_id}/'),
            'delete_crew': ('DELETE', f'crews/{resource_id}/'),

            # Tool operations
            'list_tools': ('GET', 'tools/'),
            'get_tool': ('GET', f'tools/{resource_id}/'),
            'create_tool': ('POST', 'tools/'),
            'update_tool': ('PUT', f'tools/{resource_id}/'),
            'delete_tool': ('DELETE', f'tools/{resource_id}/'),
        }

        if operation not in operation_map:
            raise ValueError(f"Invalid operation: {operation}")

        method, endpoint = operation_map[operation]

        # Validate resource_id for operations that require it
        if 'get_' in operation or 'update_' in operation or 'delete_' in operation:
            if not resource_id:
                raise ValueError(f"resource_id is required for operation: {operation}")

        # Validate data for create/update operations
        if method in ['POST', 'PUT'] and not data:
            raise ValueError(f"data is required for operation: {operation}")

        return self._make_request(method, endpoint, data)