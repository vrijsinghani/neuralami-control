from django import template
from django.utils.safestring import mark_safe
from apps.organizations.utils import get_current_organization

register = template.Library()

@register.simple_tag
def organization_context_indicator(resource_type="resource"):
    """
    Displays an organization context indicator for forms that create new resources.
    
    Args:
        resource_type (str): The type of resource being created (e.g., "client", "project")
        
    Returns:
        HTML markup for the organization context indicator
    """
    organization = get_current_organization()
    if not organization:
        return ""
    
    html = """
    <div class="alert alert-info d-flex align-items-center organization-context-alert">
        <i class="fas fa-building me-2"></i>
        <div>
            Creating new {resource_type} in <strong>{org_name}</strong>
        </div>
    </div>
    """.format(
        resource_type=resource_type,
        org_name=organization.name
    )
    
    return mark_safe(html)

@register.simple_tag
def organization_name():
    """
    Returns the name of the current organization or placeholder text if none.
    """
    organization = get_current_organization()
    if organization:
        return organization.name
    return "No Organization" 