import requests

# Clean string structure with explicit target parameters
target_url = "http://127.0.0"
payload_params = {
    "url": "https://google.com",
    "email": "ram@test.local"
}

try:
    print("Dispatching payload over to Flask network module...")
    response = requests.get(target_url, params=payload_params, allow_redirects=False)
    print(f"Network Handshake Status Code: {response.status_code}")
    print("Success! Now check your tracker.py terminal window.")
except Exception as e:
    print(f"Connection failure. Make sure tracker.py is running. Error details: {e}")
