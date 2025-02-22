from django import template
import json as json_lib

register = template.Library()

@register.filter
def index(indexable, i):
    """Get item at index i from an indexable object"""
    try:
        return indexable[i]
    except (IndexError, TypeError, KeyError):
        return ''

@register.filter
def json(value):
    """Convert a Python object to a JSON string"""
    try:
        return json_lib.dumps(value)
    except (TypeError, ValueError):
        return '{}' 