from django import template

register = template.Library()

@register.filter
def has_force_output_enabled(agent, tool):
    """Template filter to check if force output is enabled for a tool."""
    if not agent:
        return False
    tool_setting = agent.tool_settings.filter(tool=tool).first()
    return tool_setting.force_output_as_result if tool_setting else False 