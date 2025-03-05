#!/bin/bash

# Directory to search (assuming we're in the project root)
SEARCH_DIR="apps/agents"

# Function to make replacements in a file
replace_in_file() {
    local file="$1"
    
    # Create a temporary file
    temp_file=$(mktemp)
    
    # Make the replacements
    sed -E '
        s/from crewai\.tools import BaseTool/from apps.agents.tools.base_tool import BaseTool/g
        s/from crewai\.tools\.tool_usage_events import ToolUsageError/from apps.agents.tools.base_tool import ToolUsageError/g
        s/from crewai\.tools import tool/from apps.agents.tools.base_tool import tool/g
        s/from crewai\.tools import Tool/from apps.agents.tools.base_tool import Tool/g
    ' "$file" > "$temp_file"
    
    # Check if changes were made
    if ! cmp -s "$file" "$temp_file"; then
        echo "Updated: $file"
        mv "$temp_file" "$file"
    else
        rm "$temp_file"
    fi
}

# Find all Python files and process them
find "$SEARCH_DIR" -type f -name "*.py" | while read -r file; do
    # Skip the minimal_tools.py and base_tool.py files themselves
    if [[ "$file" != *"minimal_tools.py" && "$file" != *"base_tool.py" ]]; then
        replace_in_file "$file"
    fi
done

echo "Import replacement complete!" 