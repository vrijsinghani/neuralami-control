import os
import requests
from typing import Any, Type, List, Dict, Tuple
from pydantic.v1 import BaseModel, Field
from crewai_tools.tools.base_tool import BaseTool


class KeywordsInput(BaseModel):
    keywords: List[str] = Field(description="list of keywords")
    filters: List[Tuple[str, str, float]] = Field(description="list of filters")


class KeywordsForSiteTool(BaseTool):
    name: str = "Keywords for Site"
    description: str = "Provides a list of keywords relevant to the target domain. Each keyword is supplied with relevant categories, search volume data for the last month, cost-per-click, competition, and search volume trend values for the past 12 months"
    args_schema: Type[BaseModel] = BaseModel

    def _run(self, target: str, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_site/live"
        payload = [
            {
                "target": target,
                "language_code": "en",
                "location_code": 2840,
            }
        ]
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, auth=cred)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        results = response.json()
        return results["tasks"][0]["result"]

    async def _arun(self, target: str, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordsForSiteTool does not support async")


class KeywordSuggestionsTool(BaseTool):
    name: str = "Keyword Suggestions"
    description: str = "Provides a list of keywords relevant to the target domain. Each keyword is supplied with relevant categories, search volume data for the last month, cost-per-click, competition, and search volume trend values for the past 12 months"
    args_schema: Type[BaseModel] = BaseModel

    def _run(self, seed_keyword: str, filters: List = None, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_suggestions/live"
        payload = [
            {
                "keyword": seed_keyword,
                "location_code": 2840,
                "language_code": "en",
                "include_serp_info": True,
                "include_seed_keyword": True,
                "limit": 50,
            }
        ]
        if filters:
            payload[0]["filters"] = filters
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, auth=cred)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        results = response.json()
        return results

    async def _arun(self, seed_keyword: str, filters: List = None, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordSuggestionsTool does not support async")


class KeywordIdeasTool(BaseTool):
    name: str = "Keyword Ideas"
    description: str = "Provides search terms that are relevant to the product or service categories of the specified keywords. The algorithm selects the keywords which fall into the same categories as the seed keywords specified"
    args_schema: Type[BaseModel] = KeywordsInput

    def _run(self, keywords: List[str], filters: List[str] = None, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
        payload = [
            {
                "keywords": keywords,
                "location_code": 2840,
                "language_code": "en",
                "include_serp_info": True,
                "limit": 100,
            }
        ]
        payload[0]["order_by"] = "keyword_info.search_volume,desc"
        if filters:
            payload[0]["filters"] = filters
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, auth=cred)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        results = response.json()
        return results

    async def _arun(self, keywords: List[str], filters: List[str] = None, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordIdeasTool does not support async")


class KeywordTools:
    @staticmethod
    def tools():
        return [KeywordsForSiteTool(), KeywordSuggestionsTool(), KeywordIdeasTool()]

    @staticmethod
    def _dataforseo_credentials():
        login = os.environ["DATAFORSEO_LOGIN"]
        password = os.environ["DATAFORSEO_PASSWORD"]
        return login, password
