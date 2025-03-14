from django import template
import json
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='replace_value')
def replace_value(value, arg):
    """Removes all values of arg from the given string"""
    return value.replace(arg, ' ').title()

@register.filter(name='clean_title')
def clean_title(text):
    return text.replace('#','').strip().replace('\n','').replace('\r,','')

@register.filter(name='dict2json')
def dict_to_json(dictionary):
    return json.dumps(dictionary)

@register.simple_tag
def client_data(client):
    client_json = json.dumps(client)
    return mark_safe(client_json) 