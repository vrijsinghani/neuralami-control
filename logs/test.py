import requests
import json

# API Configuration
API_BASE_URL = "https://api.rfms.online/v2/"
USER_NAME = "1017@eef0f8b6-0212-40bd-8cd7-424f12d8b501"
API_KEY = "p*RW%q3$Qs4XtzDDjTIC"
STORE_ID = "store-10ab0f1e76f7499892cdfa5eeaeb523d"

# Location data
locations = {
    "68": "Duncanville",
    "71": "Garland",
    "70": "Arlington"
}

def get_session_token():
    """Get session token using credentials"""
    auth_url = f"{API_BASE_URL}"
    headers = {
        "Content-Type": "application/json"
    }
    auth_data = {
        "userName": USER_NAME,
        "apiKey": API_KEY
    }

    try:
        response = requests.post(auth_url, headers=headers, json=auth_data)
        response.raise_for_status()
        return response.json().get("sessionToken")
    except requests.exceptions.RequestException as e:
        print(f"Error getting session token: {e}")
        return None

def make_api_request(session_token):
    """Make a sample API request"""
    # Example endpoint - adjust according to your needs
    endpoint = f"{API_BASE_URL}stores/{STORE_ID}/locations"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {session_token}"
    }

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
        return None

def main():
    # Get session token
    print("Getting session token...")
    session_token = get_session_token()

    if not session_token:
        print("Failed to get session token")
        return

    print("Session token obtained successfully")

    # Make API request
    print("\nMaking API request...")
    response_data = make_api_request(session_token)

    if response_data:
        print("\nAPI Response:")
        print(json.dumps(response_data, indent=2))

if __name__ == "__main__":
    main()

# No files are created or modified during execution