import requests
import json

try:
    response = requests.get("http://localhost:8001/v1/models")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
