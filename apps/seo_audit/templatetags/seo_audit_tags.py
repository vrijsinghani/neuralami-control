from django import template

register = template.Library()

@register.filter
def is_string(value):
    """Check if a value is a string."""
    return isinstance(value, str) 