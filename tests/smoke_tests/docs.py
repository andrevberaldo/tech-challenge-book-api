import requests
import os

API_URL = os.getenv("API_URL", "http://localhost:4000")
VERSION_URL = f"{API_URL}/version"
DOCS_URL = f"{API_URL}/docs"

def test_version():
    response = requests.get(VERSION_URL)
    git_hash = os.getenv("GIT_HASH")
    api_hash = response.json()["version"]

    if git_hash and (git_hash != api_hash):
        raise Exception(f"The api version (${api_hash}) is different than the expected (${git_hash})")

    print(f"[VERSION] ✅ Successfully accessed version - {api_hash}")


def test_docs_route():
    try:
        response = requests.get(DOCS_URL)
        response.raise_for_status()
        print("[DOCS] ✅ Successfully accessed API Docs")        
    except requests.exceptions.RequestException as e:
        print("[DOCS] ❌ Request Error:", e)


