import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

class TableFormatter:
    @staticmethod
    def detect_tabular_data(data: Any) -> bool:
        """Detect if data appears to be tabular"""
        try:
            # Handle string input
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    return False

            # Handle dictionary with nested data
            if isinstance(data, dict):
                # Look for common response patterns and nested data
                for key in ['data', 'results', 'search_console_data', 'analytics_data', 
                           'records', 'rows', 'items', 'response']:
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
                # If no list found in known keys, check all values
                if isinstance(data, dict):
                    for value in data.values():
                        if isinstance(value, list) and len(value) > 0:
                            data = value
                            break

            # Check if it's a list of dictionaries with consistent structure
            if isinstance(data, list) and len(data) > 0:
                if all(isinstance(item, dict) for item in data):
                    # Get keys from first item
                    keys = set(data[0].keys())
                    # Check if all items have same keys and at least one key
                    return len(keys) > 0 and all(set(item.keys()) == keys for item in data)

            return False
            
        except Exception as e:
            logger.error(f"Error detecting tabular data: {str(e)}")
            return False