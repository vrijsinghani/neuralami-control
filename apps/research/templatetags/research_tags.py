from django import template

register = template.Library()

@register.filter
def index(indexable, i):
    """Get item at index i from an indexable object"""
    try:
        return indexable[i]
    except (IndexError, TypeError, KeyError):
        return '' 