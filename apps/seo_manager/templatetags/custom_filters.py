from django import template
from datetime import datetime

register = template.Library()

@register.filter(name='format_iso_date')
def format_iso_date(value, format_string):
  try:
      date = datetime.fromisoformat(value)
      return date.strftime(format_string)
  except (ValueError, TypeError):
      return value  # Return the original value if parsing fails