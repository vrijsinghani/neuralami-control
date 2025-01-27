from django import template
from django.template.defaultfilters import stringfilter
import os
from urllib.parse import quote

register = template.Library()

@register.filter
@stringfilter
def file_extension(value):
    """Returns the file extension from a path."""
    return os.path.splitext(value)[1][1:].lower()

@register.filter
@stringfilter
def info_value(path):
    """Returns stored info for a file path."""
    from apps.file_manager.models import FileInfo
    try:
        file_info = FileInfo.objects.get(path=path)
        return file_info.info
    except FileInfo.DoesNotExist:
        return ''

@register.filter
def encoded_file_path(path):
    return path.replace('/', '%slash%')

@register.filter
def encoded_path(path):
    return path.replace('\\', '/')