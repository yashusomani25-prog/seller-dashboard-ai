import requests

# Forcing localhost to clear any hidden Windows network path routing bugs
gateway_url = "http://localhost:8080/api/v1/send"

payload = {
    "client_id": "nepal_wallet_01",
    "secret_key": "key_secret_777",
    "email": "ram@test.local",
    "name": "Ram Bahadur",
    "code": "API_NODE_SUCCESS_99"
}

try:
    print("Corporate app hitting your Private Mailer API via localhost...")
    response = requests.post(gateway_url, json=payload)
    print(f"API Server Response Status: {response.status_code}")
    print(f"API Body Print: {response.json()}")
except Exception as e:
    print(f"Failed to connect to gateway architecture. Details: {e}")
