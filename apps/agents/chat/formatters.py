from typing import Any, Dict, List, Union
import json
import logging

logger = logging.getLogger(__name__)

class TableFormatter:
    """Generic table formatter for structured data"""
    
    @staticmethod
    def _is_json(data: str) -> bool:
        """Check if string is valid JSON"""
        try:
            json.loads(data)
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def _is_csv(data: str) -> bool:
        """Check if string appears to be CSV data"""
        if not isinstance(data, str):
            return False
        return (',' in data and 
                '\n' in data and 
                '{' not in data and 
                '[' not in data)

    @staticmethod
    def _parse_csv(csv_data: str) -> List[Dict]:
        """Convert CSV string to list of dictionaries"""
        try:
            lines = csv_data.strip().split('\n')
            headers = [h.strip() for h in lines[0].split(',')]
            
            return [
                {
                    headers[i]: value.strip() 
                    for i, value in enumerate(line.split(','))
                    if i < len(headers)
                }
                for line in lines[1:]
            ]
        except Exception as e:
            logger.error(f"Error parsing CSV: {str(e)}", exc_info=True)
            return []

    @staticmethod
    def _find_tabular_data(data: Any) -> Union[List[Dict], None]:
        """
        Recursively search for tabular data in the structure.
        Returns the first found list of dictionaries with consistent keys.
        """
        # Handle string input
        if isinstance(data, str):
            if TableFormatter._is_json(data):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    return None
            elif TableFormatter._is_csv(data):
                return TableFormatter._parse_csv(data)
            else:
                return None

        # Handle list of dictionaries
        if isinstance(data, list) and data:
            if all(isinstance(item, dict) for item in data):
                # Get all unique keys from all objects
                keys = set().union(*(item.keys() for item in data))
                if keys:  # If we have keys, it's tabular
                    return data
            
            # Check each list item for nested tabular data
            for item in data:
                result = TableFormatter._find_tabular_data(item)
                if result:
                    return result

        # Handle dictionary
        if isinstance(data, dict):
            # First check direct values
            for value in data.values():
                if isinstance(value, list) and value:
                    if all(isinstance(item, dict) for item in value):
                        return value
            
            # Then check nested structures
            for value in data.values():
                result = TableFormatter._find_tabular_data(value)
                if result:
                    return result

        return None

    @staticmethod
    def detect_tabular_data(data: Any) -> bool:
        """Detect if data contains tabular structure anywhere in the hierarchy"""
        try:
            return TableFormatter._find_tabular_data(data) is not None
        except Exception:
            logger.error("Error detecting tabular data", exc_info=True)
            return False

    @staticmethod
    def format_table(data: Any) -> str:
        """Format tabular data into a markdown table"""
        try:
            tabular_data = TableFormatter._find_tabular_data(data)
            if not tabular_data:
                return str(data)

            # Get all unique keys from all objects
            keys = list(set().union(*(item.keys() for item in tabular_data)))
            
            # Calculate column widths
            col_widths = {key: len(str(key)) for key in keys}
            for row in tabular_data:
                for key in keys:
                    value = row.get(key)
                    if value is None:
                        continue
                    elif isinstance(value, (dict, list)):
                        str_value = json.dumps(value)
                    else:
                        str_value = str(value)
                    col_widths[key] = max(col_widths[key], len(str_value))

            # Build table
            # Header row
            table = "| " + " | ".join(
                str(key).ljust(col_widths[key]) 
                for key in keys
            ) + " |\n"
            
            # Separator row
            table += "|" + "|".join(
                "-" * (col_widths[key] + 2) 
                for key in keys
            ) + "|\n"
            
            # Data rows
            for row in tabular_data:
                table += "| " + " | ".join(
                    str(row.get(key, '')).ljust(col_widths[key]) 
                    for key in keys
                ) + " |\n"

            return table

        except Exception as e:
            logger.error(f"Error formatting table: {str(e)}", exc_info=True)
            return str(data)  # Return original data if formatting fails