from django import template
import os

register = template.Library()

@register.filter
def file_extension(value):
    """Returns the file extension of a file path."""
    _, extension = os.path.splitext(value)
    return extension.lower()


@register.filter
def encoded_file_path(path):
    """Encodes slashes in a file path for use in URLs."""
    if path:
        return path.replace('/', '%slash%')
    return path

@register.filter
def encoded_path(path):
    """Encodes a path for use in URLs."""
    if path:
        # First normalize path separators
        path = path.replace('\\', '/')
        # Then URL encode the path
        from urllib.parse import quote
        # Make sure to encode slashes as well
        return quote(path, safe='')
    return path

@register.filter
def info_value(value):
    """Returns the info value for a file path."""
    from apps.file_manager.models import FileInfo
    try:
        file_info = FileInfo.objects.get(path=value)
        return file_info.info
    except FileInfo.DoesNotExist:
        return ""

@register.filter
def filename(value):
    """Returns the filename from a path."""
    if value:
        return os.path.basename(value)
    return value