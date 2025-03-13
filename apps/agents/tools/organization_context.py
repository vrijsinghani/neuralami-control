import logging
import functools
from typing import Any, Dict, Optional, Type
from crewai.tools import BaseTool
from pydantic import Field, model_validator

from apps.organizations.utils import OrganizationContext

logger = logging.getLogger(__name__)

class OrganizationAwareToolMixin:
    """
    A mixin to make tools organization-aware.
    
    This mixin adds organization_id as a parameter to tools and ensures
    that organization context is properly set during tool execution.
    """
    organization_id: Optional[str] = Field(
        default=None,
        description="ID of the organization context for this tool execution"
    )
    
    @model_validator(mode='after')
    def _validate_organization(self):
        """Validate that organization_id is properly set"""
        if not self.organization_id:
            # If no organization_id, try to get from current context
            current_org = OrganizationContext.get_current()
            if current_org:
                self.organization_id = str(current_org.id)
                logger.debug(f"Using organization from current context: {self.organization_id}")
        
        return self
    
    def _run_with_org_context(self, original_run, **kwargs):
        """Run the tool with organization context set"""
        if not self.organization_id:
            logger.warning(
                f"Tool {self.__class__.__name__} executed without organization_id. "
                "Organization context will not be set."
            )
            return original_run(**kwargs)
            
        try:
            with OrganizationContext.organization_context(self.organization_id):
                logger.debug(f"Running tool {self.__class__.__name__} with organization_id: {self.organization_id}")
                return original_run(**kwargs)
        except Exception as e:
            logger.exception(
                f"Error in tool {self.__class__.__name__} "
                f"with organization_id {self.organization_id}: {str(e)}"
            )
            raise

def make_tool_organization_aware(tool_cls: Type[BaseTool]) -> Type[BaseTool]:
    """
    Factory function to create organization-aware versions of existing tools.
    
    Example:
        # Create an organization-aware version of an existing tool
        OrganizationAwareSEOCrawlerTool = make_tool_organization_aware(SEOCrawlerTool)
        
        # Use it with organization context
        tool = OrganizationAwareSEOCrawlerTool(organization_id=org.id)
        result = tool.run(website_url="https://example.com")
    """
    # Create a new class inheriting from the original tool and the mixin
    class OrganizationAwareTool(OrganizationAwareToolMixin, tool_cls):
        """
        Organization-aware version of {tool_cls.__name__}.
        Automatically handles organization context during execution.
        """
        
        def __init__(self, **data):
            super().__init__(**data)
            
            # Store original _run method
            self._original_run = super()._run
            
            # Override _run method with organization-aware version
            self._run = functools.partial(self._run_with_org_context, self._original_run)
            
    # Set appropriate name and docstring
    OrganizationAwareTool.__name__ = f"OrganizationAware{tool_cls.__name__}"
    OrganizationAwareTool.__doc__ = f"Organization-aware version of {tool_cls.__name__}."
    
    return OrganizationAwareTool 