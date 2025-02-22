#test endpoing
import requests

# Define API constants
base_url = "https://api.rfms.online/v2/"  # Note the trailing slash
username = "1017@eef0f8b6-0212-40bd-8cd7-424f12d8b501"
api_key = "p*RW%q3$Qs4XtzDDjT!C"
store_id = "store-10ab0f1e76f7499892cdfa5eeaeb523d"

# Step 1: Authenticate to get session token
login_url = base_url 
payload = {
    "username": username,
    "api_key": api_key
}

print("Attempting to authenticate...")
response = requests.post(login_url, json=payload)

# Check if authentication was successful
if response.status_code == 200:
    token = response.json().get("token")
    if token:
        print("Successfully obtained session token:", token)
    else:
        print("Error: Token not found in response:", response.text)
        exit()
else:
    print(f"Authentication failed with status {response.status_code}:", response.text)
    exit()

# Step 2: Hit the store locations endpoint with the token
locations_url = base_url + f"stores/{store_id}/locations"
headers = {
    "Authorization": f"Bearer {token}"
}

print(f"Requesting locations from {locations_url}...")
locations_response = requests.get(locations_url, headers=headers)

# Check if the request was successful
if locations_response.status_code == 200:
    locations = locations_response.json()
    print("Locations retrieved successfully:")
    print(locations)
else:
    print(f"Failed to retrieve locations with status {locations_response.status_code}:", locations_response.text)