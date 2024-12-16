from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from pandasai import Agent as PandasAgent
from pandasai.llm import BambooLLM
import pandas as pd
import os

class PandasAIToolInput(BaseModel):
    """Schema for PandasAI tool inputs"""
    query: str = Field(..., description="The natural language query to analyze the data")
    data_source: str = Field(..., description="Path to data file or DataFrame variable name")
    data_format: str = Field(default="csv", description="Format of data source (csv, excel, parquet)")
    
class PandasAITool:
    """Tool for analyzing data using PandasAI"""
    name = "pandas_ai_analyzer"
    description = "Analyze data using natural language queries through PandasAI"
    args_schema = PandasAIToolInput

    def __init__(self):
        # Initialize with BambooLLM by default
        self.llm = BambooLLM(api_key=os.getenv("PANDASAI_API_KEY"))
        
    def _load_data(self, data_source: str, data_format: str) -> pd.DataFrame:
        """Load data from various sources"""
        if data_format == "csv":
            return pd.read_csv(data_source)
        elif data_format == "excel":
            return pd.read_excel(data_source)
        elif data_format == "parquet":
            return pd.read_parquet(data_source)
        else:
            raise ValueError(f"Unsupported data format: {data_format}")

    async def _run(
        self,
        query: str,
        data_source: str,
        data_format: str = "csv"
    ) -> str:
        """Execute PandasAI analysis"""
        try:
            # Load the data
            df = self._load_data(data_source, data_format)
            
            # Initialize PandasAI agent
            agent = PandasAgent(df, config={"llm": self.llm})
            
            # Run the query
            response = agent.chat(query)
            
            return str(response)
            
        except Exception as e:
            return f"Error analyzing data: {str(e)}" 