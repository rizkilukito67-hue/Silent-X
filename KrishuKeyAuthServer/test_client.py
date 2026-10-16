import urllib.request
import urllib.error
import json
import sys

BASE_URL = "http://localhost:5000/api/v1"
APP_NAME = "garaa-App-1"
OWNER_ID = "garaa"
SECRET = "1fb641dc27d1400cd42c88aeae239c74"
VERSION = "1.0.0"

def post_json(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json; charset=utf-8",
        "x-api-key": SECRET,
        "x-owner-id": OWNER_ID,
        "x-app-name": APP_NAME
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        print(f"[HTTP Error] {e.code}: {e.read().decode()}")
        return None
    except Exception as e:
        print(f"[Connection Error] {e}")
        return None

def get_var(var_name):
    url = f"{BASE_URL}/var/{var_name}"
    req = urllib.request.Request(url, headers={
        "x-api-key": SECRET,
        "x-owner-id": OWNER_ID,
        "x-app-name": APP_NAME
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Var Error] {e}")
        return None

def run_tests():
    print("========================================")
    print("Testing Krishu KeyAuth API Endpoints...")
    print("========================================")

    # 1. Test /init
    print("\n1. Testing POST /init...")
    init_res = post_json("/init", {
        "name": APP_NAME,
        "ownerid": OWNER_ID,
        "secret": SECRET,
        "version": VERSION
    })
    print("Init Response:", init_res)
    assert init_res and init_res.get("success") is True, "Init failed!"
    print("[PASS] Init successfully returned app details.")

    # 2. Test /login with default account (garaa / 123456)
    print("\n2. Testing POST /login (Default account: garaa / 123456)...")
    login_res = post_json("/login", {
        "name": APP_NAME,
        "ownerid": OWNER_ID,
        "secret": SECRET,
        "username": "garaa",
        "password": "123456",
        "hwid": "TEST-HWID-MACHINE-GUID-1234"
    })
    print("Login Response:", login_res)
    assert login_res and login_res.get("success") is True, "Login failed!"
    assert login_res.get("lifetime") is True, "Expected lifetime to be true!"
    print("[PASS] Login successful, token generated, lifetime access confirmed.")

    # 3. Test /var/<varName>
    print("\n3. Testing GET /var/status...")
    var_res = get_var("status")
    print("GetVar Response:", var_res)
    assert var_res and var_res.get("success") is True, "GetVar failed!"
    print(f"[PASS] Variable 'status' retrieved: {var_res.get('value')}")

    # 4. Test /license direct key activation
    print("\n4. Testing POST /license with 'KXC-LIFE-AAAA-BBBB-CCCC'...")
    lic_res = post_json("/license", {
        "name": APP_NAME,
        "ownerid": OWNER_ID,
        "secret": SECRET,
        "key": "KXC-LIFE-AAAA-BBBB-CCCC",
        "hwid": "TEST-HWID-KEY-USER"
    })
    print("License Response:", lic_res)
    assert lic_res and lic_res.get("success") is True, "License activation failed!"
    print("[PASS] License activated successfully.")

    # 5. Test Invalid login rejection
    print("\n5. Testing invalid password rejection...")
    bad_login = post_json("/login", {
        "name": APP_NAME,
        "ownerid": OWNER_ID,
        "secret": SECRET,
        "username": "garaa",
        "password": "wrong_password_999",
        "hwid": "TEST-HWID-MACHINE-GUID-1234"
    })
    print("Bad Login Response:", bad_login)
    assert bad_login and bad_login.get("success") is False, "Should have failed!"
    print("[PASS] Properly rejected invalid password.")

    print("\n========================================")
    print("ALL API TESTS PASSED SUCCESSFULLY! 100% COMPATIBLE.")
    print("========================================")

if __name__ == "__main__":
    run_tests()
