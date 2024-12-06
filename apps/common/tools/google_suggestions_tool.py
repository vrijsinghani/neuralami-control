from crewai_tools import tool
import requests
import xml.etree.ElementTree as ET

@tool("Google Suggestions")
def google_suggestions_tool(argument: str) -> str:
    """Retrieve Google search suggestions for a given keyword."""
    # Parse the argument to extract the keyword and other parameters
    keyword = argument.split(",")[0].strip()
    country_code = argument.split(",")[1].strip() if "," in argument else "us"

    # Build the Google Search query URL
    search_query = f"is {keyword}"
    google_search_url = f"http://google.com/complete/search?output=toolbar&gl={country_code}&q={search_query}"

    # Call the URL and read the data
    result = requests.get(google_search_url)
    tree = ET.ElementTree(ET.fromstring(result.content))
    root = tree.getroot()

    # Extract the suggestions from the XML response
    suggestions = []
    for suggestion in root.findall('CompleteSuggestion'):
        question = suggestion.find('suggestion').attrib.get('data')
        suggestions.append(question)

    # Return the suggestions as a comma-separated string
    return ", ".join(suggestions)
