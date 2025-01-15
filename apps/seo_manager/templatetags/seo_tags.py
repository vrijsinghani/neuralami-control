from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using bracket notation"""
    return dictionary.get(key)

@register.filter
def get_initial_rank(project, keyword):
    """Get initial rank for a keyword from a project"""
    return project.get_initial_rank(keyword)
