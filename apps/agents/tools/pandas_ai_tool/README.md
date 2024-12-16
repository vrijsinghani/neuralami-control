# PandasAI Tool

A CrewAI tool for data analysis using PandasAI with natural language queries.

## Features

- Natural language data analysis
- Multiple data format support (CSV, Excel, Parquet)
- Configurable analysis depth
- Comprehensive error handling
- Detailed logging
- Structured JSON responses

## Usage
python
from apps.agents.tools.pandas_ai_tool import PandasAITool

tool = PandasAITool()
result = tool.run(
    query="What is the average age by category?",
    data_source="path/to/data.csv",
    data_format="csv",
    analysis_depth="detailed"
)


## Configuration

Set the following environment variables:
- PANDASAI_API_KEY: Your PandasAI API key
- PANDAS_AI_MODEL: The model to use for analysis (optional)

This implementation:
Follows the same structural patterns as the compression tool
Includes comprehensive error handling
Provides detailed logging
Uses structured input/output schemas
Supports different analysis depths
Includes proper documentation
Follows Django project conventions
Implements proper type hinting
Uses environment variables for configuration
