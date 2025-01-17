from typing import Any, Optional, Type 
from typing import Any, Optional
from pydantic import BaseModel, Field
from crewai.tools.base_tool import BaseTool
from apps.seo_manager.models import UserActivity
import logging

logger = logging.getLogger(__name__)

"""
You can use the UserActivityTool by 
 1. importing 'from apps.common.tools.user_activity_tool import user_activity_tool' and 
 2. calling its run method with the required arguments: 'result = user_activity_tool.run(user=user, category=category, action=action, client=client, details=details)'
"""

class UserActivityToolSchema(BaseModel):
    """Input schema for UserActivityTool."""
    user: Any = Field(..., description="The user performing the action.")
    category: str = Field(..., description="The category of the action.")
    action: str = Field(..., description="The action performed.")
    client: Optional[Any] = Field(None, description="The client associated with the action (optional).")
    details: Optional[str] = Field(None, description="Additional details about the action (optional).")

class UserActivityTool(BaseTool):
    name: str = "Log User Activity"
    description: str = "Logs user activity in the system."
    args_schema: Type[BaseModel] = UserActivityToolSchema
    
    def _run(
        self, 
        user: Any,
        category: str,
        action: str,
        client: Optional[Any] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ) -> Any:
        try:
            UserActivity.objects.create(
                user=user,
                client=client,
                category=category,
                action=action,
                details=details
            )
            logger.debug(f"User activity logged: {user.username} - {category} - {action} - {client} - {details}")
            return {"success": True, "message": "User activity logged successfully."}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Initialize the tool
user_activity_tool = UserActivityTool()