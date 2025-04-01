import requests
from bs4 import BeautifulSoup
from apps.agents.tools.business_credibility_tool.business_credibility_tool import BusinessCredibilityTool
import json

# 1. Fetch website content
url = "https://neuralami.com"
# Define a common browser User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
try:
    # Add the headers= parameter to the request
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status() # Raise an exception for bad status codes
    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text(separator=' ', strip=True)
    print(f"Successfully fetched content from {url}")
except requests.exceptions.RequestException as e:
    print(f"Error fetching {url}: {e}")
    # Exit or handle error as appropriate
    exit()

# 2. Instantiate the tool
tool = BusinessCredibilityTool()

# 3. Run the tool
print("Running BusinessCredibilityTool...")
try:
    result_json = tool._run(text_content=text_content, html_content=html_content)
    # import json # No need to import here again
    result_dict = json.loads(result_json)
    
    # 4. Print the results nicely
    print("\n--- Business Credibility Tool Results ---")
    print(json.dumps(result_dict, indent=2))
    print("----------------------------------------")

except Exception as e:
    print(f"Error running BusinessCredibilityTool: {e}")
