"""
test_rbac_multiuser.py — Multi-user role / portal separation.
Verifies each seeded role user can log in and gets the correct portal list,
and cannot access portals outside their role.

Run: REACT_APP_BACKEND_URL=<url> python -m pytest tests/test_rbac_multiuser.py -q
Requires the production seed (creates role users) to have been run.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PWD = "Dewi@123"

_PORTAL_CACHE = {}

# email -> (must_include_portals, must_exclude_portals)
ROLE_EXPECTATIONS = {
    "hr@dewiaditya.id":      (["hr", "self"],        ["finance", "warehouse", "maklon", "toko"]),
    "finance@dewiaditya.id": (["finance", "assets"], ["hr", "warehouse", "toko"]),
    "spv@dewiaditya.id":     (["production", "maklon", "rnd"], ["finance", "hr"]),
    "gudang@dewiaditya.id":  (["warehouse", "accessories"],   ["finance", "hr", "toko"]),
    "maklon@dewiaditya.id":  (["maklon"],            ["finance", "hr", "warehouse"]),
}


def _login_portals(email, password=PWD):
    if email in _PORTAL_CACHE:
        return _PORTAL_CACHE[email]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text[:200]}"
    data = r.json()
    res = (data.get("portals", []), data)
    _PORTAL_CACHE[email] = res
    return res


@pytest.mark.parametrize("email", list(ROLE_EXPECTATIONS.keys()))
def test_role_login_and_portals(email):
    include, exclude = ROLE_EXPECTATIONS[email]
    portals, data = _login_portals(email)
    assert "token" in data, f"No token for {email}"
    for p in include:
        assert p in portals, f"{email} ({data['user']['role']}) should access '{p}', got {portals}"
    for p in exclude:
        assert p not in portals, f"{email} ({data['user']['role']}) should NOT access '{p}', got {portals}"


def test_self_and_collaboration_for_all_roles():
    for email in ROLE_EXPECTATIONS:
        portals, _ = _login_portals(email)
        assert "self" in portals, f"{email} missing 'self' portal"
        assert "collaboration" in portals, f"{email} missing 'collaboration' portal"


def test_admin_sees_all_portals():
    portals, _ = _login_portals("admin@garment.com", "Admin@123")
    for p in ("management", "production", "warehouse", "finance", "hr", "maklon", "toko", "rnd"):
        assert p in portals, f"admin missing portal '{p}'"
