from .scrapper_tool import ScrapperTool, ScrapperToolSchema, OutputType

# Make classes available at both module and submodule level
scrapper_tool = ScrapperTool  # This allows "scrapper_tool.scrapper_tool" to work
scrapper_tool_schema = ScrapperToolSchema

__all__ = ['ScrapperTool', 'ScrapperToolSchema', 'OutputType', 'scrapper_tool', 'scrapper_tool_schema'] 