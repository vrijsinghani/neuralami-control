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
    """Return the basename of a path."""
    return os.path.basename(str(value))

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary."""
    return dictionary.get(key, '')

@register.filter
def dictsortby(value, arg):
    """Return a list of dictionaries sorted by the given key."""
    if not value:
        return []
    return [item for item in value if arg in item and item[arg]]
