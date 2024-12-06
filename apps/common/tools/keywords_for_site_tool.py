import os
import requests
from crewai import Agent
from langchain.tools import tool

@tool("DataForSEO Keywords for Site")
def keywords_for_site_tool(target: str) -> str:
    """
    Retrieves a list of SEO keywords relevant to the specified site using the DataForSEO API.
    """
    login = os.environ["DATAFORSEO_LOGIN"]
    password = os.environ["DATAFORSEO_PASSWORD"]
    cred = (login, password)
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keywords_for_site/live"

    payload = [
        {
            "target": target,
            "language_code": "en",
            "location_code": 2840,
        }
    ]

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=payload, headers=headers, auth=cred)
    results = response.json()

    # Process the results and return the desired output
    # ...

    return results
