from django import template
import os

register = template.Library()

@register.filter
def abs_value(value):
    try:
        return abs(value)
    except (TypeError, ValueError):
        return value

@register.filter
def basename(value):
    """Get the basename of a file path"""
    return os.path.basename(value)

@register.filter
def split(value, arg):
    return value.split(arg)
