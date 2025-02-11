import os
import requests
import json
from urllib.parse import quote

def fetch_yelp_content(url):
    """
    Fetch content from Yelp using browserless (synchronous version)
    """
    browserless_api_key = "neuralamibrowserlesstoken"
    browserless_url = "https://browserless.neuralami.com"
    # Configure browserless options
    options = {
        'url': url,
        'waitFor': '.business-name',  # Wait for business listings to load
        'elements': [
            {
                'selector': '.business-name',  # Business names
                'timeout': 10000
            },
            {
                'selector': '.business-address',  # Business addresses
                'timeout': 10000
            },
            {
                'selector': '.business-phone',  # Business phone numbers
                'timeout': 10000
            }
        ],
        'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        endpoint = f"{browserless_url}/scrape?token={browserless_api_key}"
        
        response = requests.post(endpoint, json=options)
        
        if response.status_code != 200:
            print(f"Error: Failed to fetch content: {response.status_code}")
            return None
        
        data = response.json()
        
        if not data or 'data' not in data:
            print("Error: No data returned from browserless")
            return None
        
        # Process and structure the data
        businesses = []
        for element in data['data']:
            if element.get('selector') == '.business-name':
                businesses.extend(element.get('results', []))
        
        print(f"Successfully fetched {len(businesses)} businesses from Yelp")
        return businesses

    except Exception as e:
        print(f"Error fetching Yelp content: {str(e)}")
        return None

# Usage example:
def main():
    url = 'https://www.yelp.com/search?find_desc=Flooring+Stores&find_loc=Miami%2C+FL'
    results = fetch_yelp_content(url)
    if results:
        for business in results:
            print(business)

if __name__ == "__main__":
    main()