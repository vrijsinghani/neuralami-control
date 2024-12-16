# apps/agents/tools/pandas_ai_tool/pandas_ai_tool.py

import os
from typing import Any, Type, List, Dict, Optional
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
from apps.common.utils import get_llm
from pandasai import Agent as PandasAgent
from pandasai.llm import BambooLLM
import pandas as pd
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)

class PandasAIToolSchema(BaseModel):
    """Input schema for PandasAITool."""
    query: str = Field(
        ..., 
        description="The natural language query to analyze the data"
    )
    data_source: str = Field(
        ..., 
        description="Path to data file or DataFrame variable name"
    )
    data_format: str = Field(
        default="csv",
        description="Format of data source (csv, excel, parquet)"
    )
    analysis_depth: str = Field(
        default="detailed",
        description="Analysis depth: 'basic' (simple stats), 'detailed' (comprehensive analysis), or 'advanced' (complex insights)"
    )

class PandasAITool(BaseTool):
    name: str = "PandasAI Data Analysis Tool"
    description: str = """
    Analyzes data using natural language queries through PandasAI.
    Supports multiple data formats and various analysis depths.
    Features intelligent data loading, error handling, and detailed responses.
    """
    args_schema: Type[BaseModel] = PandasAIToolSchema
    
    modelname: str = Field(default=settings.PANDAS_AI_MODEL)
    llm: Optional[Any] = Field(default=None)
    pandas_agent: Optional[Any] = Field(default=None)

    def __init__(self, **data):
        super().__init__(**data)
        self.llm = BambooLLM(api_key=os.getenv("PANDASAI_API_KEY"))
        
    def _load_data(self, data_source: str, data_format: str) -> pd.DataFrame:
        """Load data from various sources with error handling."""
        try:
            loaders = {
                "csv": pd.read_csv,
                "excel": pd.read_excel,
                "parquet": pd.read_parquet
            }
            
            if data_format not in loaders:
                raise ValueError(f"Unsupported data format: {data_format}")
                
            loader = loaders[data_format]
            df = loader(data_source)
            
            logger.info(f"Successfully loaded data from {data_source}")
            logger.debug(f"DataFrame shape: {df.shape}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise

    def _get_analysis_prompt(self, analysis_depth: str, query: str) -> str:
        """Get the appropriate analysis prompt based on depth."""
        prompts = {
            "basic": f"""
            Perform a basic analysis of the data:
            - Focus on simple descriptive statistics
            - Provide clear, concise results
            - Answer the specific query: {query}
            """,
            
            "detailed": f"""
            Perform a comprehensive analysis of the data:
            - Include detailed statistical measures
            - Identify trends and patterns
            - Provide visualizations if relevant
            - Answer the specific query: {query}
            """,
            
            "advanced": f"""
            Perform an advanced analysis of the data:
            - Use sophisticated statistical methods
            - Conduct deep pattern analysis
            - Provide complex visualizations
            - Include predictive insights
            - Answer the specific query: {query}
            """
        }
        return prompts.get(analysis_depth, prompts["detailed"])

    def _run(
        self,
        query: str,
        data_source: str,
        data_format: str = "csv",
        analysis_depth: str = "detailed",
        **kwargs: Any
    ) -> str:
        try:
            # Input validation
            if not query or not data_source:
                return json.dumps({
                    "error": "Invalid input",
                    "message": "Query and data_source must be non-empty strings"
                })

            # Load the data
            df = self._load_data(data_source, data_format)
            
            # Initialize PandasAI agent if not already initialized
            if not self.pandas_agent:
                self.pandas_agent = PandasAgent(df, config={"llm": self.llm})
            
            # Get analysis prompt
            enhanced_query = self._get_analysis_prompt(analysis_depth, query)
            
            # Execute analysis
            logger.info(f"Executing analysis with depth: {analysis_depth}")
            response = self.pandas_agent.chat(enhanced_query)
            
            result = {
                "analysis_result": str(response),
                "data_info": {
                    "rows": df.shape[0],
                    "columns": df.shape[1],
                    "data_source": data_source,
                    "format": data_format
                },
                "analysis_depth": analysis_depth
            }
            
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error in PandasAITool: {str(e)}")
            return json.dumps({
                "error": "Analysis failed",
                "message": str(e)
            })
