import requests
import os
import time

BASE_URL = os.getenv("API_URL", "http://localhost:4000")
AUTH_URL = f"{BASE_URL}/api/v1/auth/login"
REFRESH_URL = f"{BASE_URL}/api/v1/auth/refresh"
PRIVATE_URL = f"{BASE_URL}/api/v1/api/private"
ADMIN_URL = f"{BASE_URL}/api/v1/admin"

def test_authentication_flow():
    test_not_authorized_login()
    accessToken, refreshToken = test_get_jwt_token()
    test_access_private_routes(accessToken)
    test_not_authorized_routes(accessToken)
    test_refresh_token(accessToken, refreshToken)


def test_not_authorized_login():
    """
        When the user is NOT registered on api and try to generate hwt token, then it should get an 403 status code.
    """
    auth_response = requests.post(AUTH_URL, auth=("unkown user", "unknown password"))

    if auth_response.status_code == 200:
        raise Exception("Expected forbidden status code for auth route")    

    print("[AUTH] ✅ Successfully blocked not authorized user to get JWT Token")
   

def test_get_jwt_token() -> tuple[str, str]:
    """
        When the user is registered on api, then it should get the accessToken and refreshToken successfully.
    """
    auth_response = requests.post(AUTH_URL, auth=("smoke", "smoke"))

    if auth_response.status_code != 200:
        raise Exception("Expected 200 status code for auth route")
    
    auth_body = auth_response.json()
    token = auth_body["accessToken"]
    refreshToken = auth_body["refreshToken"]

    if not token or not refreshToken:
        raise Exception("Expected a valid JWT Token")
    

    print("[AUTH] ✅ Successfully got JWT Token for authorized user")    

    return token, refreshToken


def test_access_private_routes(token: str):
    """
        When the user is authenticated on api, then it should be able to access private resources.
    """
    headers = {
        "Authorization": f"Bearer {token}"
    }

    guest_response = requests.get(PRIVATE_URL, headers=headers)

    if guest_response.status_code != 200:
        raise Exception("Expected to have a 200 status code for guest route")

    print("[AUTH] ✅ Successfully accessed the guest route")


def test_not_authorized_routes(token: str):
    """
        When the user is authenticated in the api but DOES NOT have autorization to access admin routes, then it should receive an unauthorized status code.
    """
    headers = {
        "Authorization": f"Bearer {token}"
    }

    admin_response = requests.get(ADMIN_URL, headers=headers)

    if admin_response.status_code != 401:
        raise Exception("Expected do NOT have access to the admin route")
    
    print("[AUTH] ✅ Successfully blocked non authorized user on admin route")


def test_refresh_token(old_access_token: str, refresh_token: str):
    time.sleep(1)

    headers = {
        "Authorization": f"Bearer {refresh_token}"
    }

    refresh_response = requests.post(REFRESH_URL, headers=headers)
    response_body = refresh_response.json()

    if refresh_response.status_code != 200:
        raise Exception(f"Expected status code to be 200, got {refresh_response.status_code}")

    new_access_token = response_body["accessToken"]
    refresh_token_response = response_body["refreshToken"]    

    if refresh_token != refresh_token_response:
        raise Exception("Expected the same Refresh token, got different")
    
    if new_access_token == old_access_token:
        raise Exception("Expected a new access token, got the same")
    
    print("[AUTH] ✅ Successfully renovated the access token")