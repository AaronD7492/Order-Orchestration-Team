"""
Comprehensive integration test suite for the Farm2Fork Order Orchestration Flask app.

Hits the running server at http://localhost:5000 directly using requests.Session()
so that cookie-based auth state is preserved across calls within a single session.

Test users (from farmforkdb):
  R267 / 6475556013
  D784 / 6475558410
  B716 / 5195559119

Run with:
  cd /Users/dilrajsooch/Order-Orchestration-Team
  python -m pytest tests/test_app.py -v
"""

import uuid
import pytest
import requests

BASE = "http://localhost:5000"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh_session():
    """Return a new requests.Session with no cookies."""
    return requests.Session()


def login_session(client_id: str, mobile: str) -> requests.Session:
    """
    Return a requests.Session that is already authenticated.
    Raises AssertionError if login fails (server or credentials problem).
    """
    s = fresh_session()
    r = s.post(
        f"{BASE}/login",
        data={"client_id": client_id, "mobile": mobile},
        allow_redirects=True,
        timeout=15,
    )
    # After a successful login the server redirects to "/" (200 HTML).
    # We verify the session cookie was set — if login.html is still in the
    # body the server rejected the credentials.
    assert r.status_code == 200, f"Login request failed: {r.status_code}"
    # Confirm we were redirected to home, not stuck on login page
    # (a login error renders login.html with the form again)
    assert "Invalid Client ID" not in r.text, (
        f"Login rejected for {client_id} — bad credentials or DB down"
    )
    return s


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def anon():
    """Un-authenticated session (fresh for every test)."""
    return fresh_session()


@pytest.fixture(scope="function")
def auth_r267():
    """Authenticated session for test user R267."""
    return login_session("R267", "6475556013")


@pytest.fixture(scope="function")
def auth_d784():
    """Authenticated session for test user D784."""
    return login_session("D784", "6475558410")


# ---------------------------------------------------------------------------
# Connectivity guard — skip the whole file if the app isn't up
# ---------------------------------------------------------------------------

def pytest_configure(config):
    pass  # nothing extra needed


@pytest.fixture(autouse=True, scope="session")
def require_server():
    """Abort early with a clear message if localhost:5000 is not reachable."""
    try:
        r = requests.get(f"{BASE}/", timeout=10)
        assert r.status_code < 500, f"Server returned {r.status_code}"
    except requests.ConnectionError:
        pytest.skip(
            "Flask app is not running at http://localhost:5000 — "
            "start it with `python -m flask run` before running these tests."
        )


# ===========================================================================
# 1. Homepage
# ===========================================================================

class TestHomepage:

    def test_homepage_loads(self, anon):
        r = anon.get(f"{BASE}/", timeout=15)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_homepage_contains_html_body(self, anon):
        r = anon.get(f"{BASE}/", timeout=15)
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


# ===========================================================================
# 2. Authentication — login / logout / /secret
# ===========================================================================

class TestAuth:

    def test_login_page_get(self, anon):
        r = anon.get(f"{BASE}/login", timeout=10)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_login_valid_credentials_r267(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"client_id": "R267", "mobile": "6475556013"},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Invalid Client ID" not in r.text

    def test_login_valid_credentials_d784(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"client_id": "D784", "mobile": "6475558410"},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Invalid Client ID" not in r.text

    def test_login_invalid_client_id(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"client_id": "XXXBAD", "mobile": "0000000000"},
            allow_redirects=True,
            timeout=15,
        )
        # Server should stay on login page and show an error
        assert r.status_code == 200
        assert "Invalid Client ID" in r.text or "invalid" in r.text.lower()

    def test_login_wrong_mobile(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"client_id": "R267", "mobile": "0000000000"},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Invalid Client ID" in r.text or "invalid" in r.text.lower()

    def test_login_missing_client_id(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"mobile": "6475556013"},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Please enter" in r.text or "required" in r.text.lower() or "Client ID" in r.text

    def test_login_missing_mobile(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={"client_id": "R267"},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Please enter" in r.text or "required" in r.text.lower()

    def test_login_missing_both_fields(self, anon):
        r = anon.post(
            f"{BASE}/login",
            data={},
            allow_redirects=True,
            timeout=15,
        )
        assert r.status_code == 200
        assert "Please enter" in r.text or "required" in r.text.lower()

    def test_logout_clears_session(self, auth_r267):
        # Confirm we are logged in first
        r = auth_r267.get(f"{BASE}/order-history", allow_redirects=False, timeout=10)
        assert r.status_code == 200  # should access the page

        # Now log out
        auth_r267.get(f"{BASE}/logout", allow_redirects=True, timeout=10)

        # After logout, order-history should redirect to /login
        r2 = auth_r267.get(f"{BASE}/order-history", allow_redirects=False, timeout=10)
        assert r2.status_code in (302, 303)
        assert "/login" in r2.headers.get("Location", "")

    def test_secret_returns_json(self, anon):
        r = anon.get(f"{BASE}/secret", timeout=15)
        assert r.status_code in (200, 503)
        data = r.json()
        if r.status_code == 200:
            assert "secret" in data
            assert isinstance(data["secret"], str)
        else:
            assert "error" in data


# ===========================================================================
# 3. Inventory API
# ===========================================================================

class TestInventoryAPI:

    def test_inventory_returns_200_or_503(self, anon):
        r = anon.get(f"{BASE}/api/inventory", timeout=30)
        assert r.status_code in (200, 503)

    def test_inventory_200_returns_items_list(self, anon):
        r = anon.get(f"{BASE}/api/inventory", timeout=30)
        if r.status_code == 503:
            pytest.skip("CIS unavailable — 503 is acceptable for flaky dependency")
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_inventory_no_zero_quantity_items(self, anon):
        r = anon.get(f"{BASE}/api/inventory", timeout=30)
        if r.status_code == 503:
            pytest.skip("CIS unavailable")
        data = r.json()
        for item in data.get("items", []):
            qty = item.get("quantityOnHand", item.get("quantity", 1))
            assert qty > 0, f"Zero-quantity item found: {item}"


# ===========================================================================
# 4. Checkout
# ===========================================================================

SAMPLE_ITEMS = [
    {"productId": "PROD-CARROTS", "productName": "Carrots", "quantity": 1.0, "unit": "kg"},
]

VALID_ADDRESS = {
    "addressLine1": "100 University Ave",
    "city": "Waterloo",
    "province": "ON",
    "postalCode": "N2L3G1",
    "dropOff": True,
}


class TestCheckoutInitiate:

    def test_initiate_valid(self, anon):
        r = anon.post(
            f"{BASE}/checkout/initiate",
            json={"items": SAMPLE_ITEMS, "userToken": "test-token"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "redirect_url" in data
        assert data["redirect_url"] == "/checkout"

    def test_initiate_missing_items_field(self, anon):
        r = anon.post(
            f"{BASE}/checkout/initiate",
            json={"userToken": "test-token"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "items" in r.json().get("error", "")

    def test_initiate_empty_items_list(self, anon):
        r = anon.post(
            f"{BASE}/checkout/initiate",
            json={"items": []},
            timeout=10,
        )
        assert r.status_code == 400

    def test_initiate_no_body(self, anon):
        r = anon.post(
            f"{BASE}/checkout/initiate",
            json=None,
            timeout=10,
        )
        assert r.status_code == 400

    def test_initiate_multiple_items(self, anon):
        items = [
            {"productId": "PROD-CARROTS", "productName": "Carrots", "quantity": 2.0, "unit": "kg"},
            {"productId": "PROD-MILK", "productName": "Milk", "quantity": 1.0, "unit": "l"},
        ]
        r = anon.post(
            f"{BASE}/checkout/initiate",
            json={"items": items},
            timeout=10,
        )
        assert r.status_code == 200


class TestCheckoutRender:

    def test_checkout_page_with_cart(self, anon):
        # First initiate a cart
        anon.post(
            f"{BASE}/checkout/initiate",
            json={"items": SAMPLE_ITEMS},
            timeout=10,
        )
        # Then render checkout
        r = anon.get(f"{BASE}/checkout", allow_redirects=False, timeout=10)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_checkout_page_without_cart_redirects(self, anon):
        r = anon.get(f"{BASE}/checkout", allow_redirects=False, timeout=10)
        # No cart in session — should redirect to /
        assert r.status_code in (302, 303)
        loc = r.headers.get("Location", "")
        # Normalize: strip trailing slash, then check — "/" stripped gives "" so check both
        assert loc in ("/", "http://localhost:5000/", "http://localhost:5000") or \
               loc.rstrip("/") in ("", "http://localhost:5000")

    def test_checkout_demo_route(self, anon):
        r = anon.get(f"{BASE}/checkout/demo", allow_redirects=True, timeout=10)
        assert r.status_code == 200


class TestCheckoutSubmit:

    def _initiate_cart(self, session, items=None):
        session.post(
            f"{BASE}/checkout/initiate",
            json={"items": items or SAMPLE_ITEMS},
            timeout=10,
        )

    def test_submit_missing_address_line1(self, anon):
        self._initiate_cart(anon)
        body = {**VALID_ADDRESS}
        del body["addressLine1"]
        r = anon.post(f"{BASE}/checkout/submit", json=body, timeout=30)
        assert r.status_code == 400
        assert "addressLine1" in r.json().get("error", "")

    def test_submit_missing_city(self, anon):
        self._initiate_cart(anon)
        body = {**VALID_ADDRESS}
        del body["city"]
        r = anon.post(f"{BASE}/checkout/submit", json=body, timeout=30)
        assert r.status_code == 400
        assert "city" in r.json().get("error", "")

    def test_submit_missing_province(self, anon):
        self._initiate_cart(anon)
        body = {**VALID_ADDRESS}
        del body["province"]
        r = anon.post(f"{BASE}/checkout/submit", json=body, timeout=30)
        assert r.status_code == 400
        assert "province" in r.json().get("error", "")

    def test_submit_no_body(self, anon):
        r = anon.post(f"{BASE}/checkout/submit", data="notjson", timeout=10,
                      headers={"Content-Type": "text/plain"})
        assert r.status_code == 400

    def test_submit_no_cart_in_session_returns_error(self, anon):
        # Fresh session with no cart — submit with items field in body
        r = anon.post(f"{BASE}/checkout/submit", json=VALID_ADDRESS, timeout=30)
        # Either 400 (no cart) or 409/503 (CIS flow failed)
        assert r.status_code in (400, 409, 503)

    def test_submit_valid_or_cis_failure(self, anon):
        """
        Full checkout flow — CIS may succeed (200) or fail due to
        out-of-stock (409) or unavailability (503). All are valid outcomes.
        """
        self._initiate_cart(anon)
        r = anon.post(f"{BASE}/checkout/submit", json=VALID_ADDRESS, timeout=60)
        assert r.status_code in (200, 409, 503)
        data = r.json()
        if r.status_code == 200:
            assert data.get("status") == "success"
            assert "f2fOrderId" in data
            assert "shippingId" in data
        elif r.status_code == 409:
            assert "error" in data
        else:
            assert "error" in data

    def test_submit_out_of_stock_product_returns_409(self, anon):
        """
        Submit a cart with a bogus product that CIS will reject.
        The app should return 409 with error == out_of_stock or a CIS error.
        """
        bogus_items = [
            {
                "productId": f"PROD-NONEXISTENT-{uuid.uuid4().hex[:6].upper()}",
                "productName": "Ghost Product",
                "quantity": 9999.0,
                "unit": "kg",
            }
        ]
        anon.post(
            f"{BASE}/checkout/initiate",
            json={"items": bogus_items},
            timeout=10,
        )
        r = anon.post(f"{BASE}/checkout/submit", json=VALID_ADDRESS, timeout=60)
        # CIS should return 409 (out of stock) or 503 (service unavailable)
        assert r.status_code in (409, 503)

    def test_submit_with_inline_items_in_body(self, anon):
        """Items can be passed directly in the submit body (no prior initiate needed)."""
        body = {
            **VALID_ADDRESS,
            "items": SAMPLE_ITEMS,
        }
        r = anon.post(f"{BASE}/checkout/submit", json=body, timeout=60)
        assert r.status_code in (200, 409, 503)


# ===========================================================================
# 5. Order History
# ===========================================================================

class TestOrderHistory:

    def test_authed_user_gets_200(self, auth_r267):
        r = auth_r267.get(f"{BASE}/order-history", timeout=10)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_authed_user_d784_gets_200(self, auth_d784):
        r = auth_d784.get(f"{BASE}/order-history", timeout=10)
        assert r.status_code == 200

    def test_unauthed_redirects_to_login(self, anon):
        r = anon.get(f"{BASE}/order-history", allow_redirects=False, timeout=10)
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("Location", "")

    def test_order_history_page_contains_html(self, auth_r267):
        r = auth_r267.get(f"{BASE}/order-history", timeout=10)
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


# ===========================================================================
# 6. Subscriptions
# ===========================================================================

class TestSubscriptions:

    def test_subscriptions_page_authed(self, auth_r267):
        r = auth_r267.get(f"{BASE}/subscriptions", allow_redirects=True, timeout=10)
        assert r.status_code == 200

    def test_subscriptions_page_unauthed_redirects(self, anon):
        r = anon.get(f"{BASE}/subscriptions", allow_redirects=False, timeout=10)
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("Location", "")

    def test_api_subscriptions_authed_returns_200_or_503(self, auth_r267):
        """C&S may be down — both 200 and 503 are acceptable from a correctly-auth'd user."""
        r = auth_r267.get(f"{BASE}/api/subscriptions", timeout=15)
        assert r.status_code in (200, 503), f"Unexpected status: {r.status_code}"

    def test_api_subscriptions_unauthed_returns_401(self, anon):
        r = anon.get(f"{BASE}/api/subscriptions", timeout=10)
        assert r.status_code == 401
        data = r.json()
        assert "error" in data

    def test_api_subscriptions_patch_unauthed_returns_401(self, anon):
        r = anon.patch(
            f"{BASE}/api/subscriptions",
            json={"subscription_id": "sub-1", "frequency": "weekly"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_api_subscriptions_delete_unauthed_returns_401(self, anon):
        r = anon.delete(
            f"{BASE}/api/subscriptions",
            json={"subscription_id": "sub-1"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_api_subscriptions_patch_authed_returns_200_or_503(self, auth_r267):
        r = auth_r267.patch(
            f"{BASE}/api/subscriptions",
            json={"subscription_id": "sub-test", "frequency": "monthly"},
            timeout=15,
        )
        assert r.status_code in (200, 400, 404, 503), f"Unexpected: {r.status_code}"

    def test_api_subscriptions_delete_authed_returns_200_or_503(self, auth_r267):
        r = auth_r267.delete(
            f"{BASE}/api/subscriptions",
            json={"subscription_id": "sub-test"},
            timeout=15,
        )
        assert r.status_code in (200, 400, 404, 503), f"Unexpected: {r.status_code}"


# ===========================================================================
# 7. Delivery Execution
# ===========================================================================

DELIVERY_ORDER_ID = f"TEST-{uuid.uuid4().hex[:8].upper()}"

DELIVERY_PAYLOAD = {
    "order_id": DELIVERY_ORDER_ID,
    "customer_name": "Test Customer",
    "address": "100 University Ave, Waterloo, ON N2L3G1",
    "items": ["Carrots", "Milk"],
    "status": "Assigned",
    "eta": "2026-04-16",
    "driver": "Driver One",
}


class TestDeliveryDashboard:

    def test_delivery_dashboard_loads(self, anon):
        r = anon.get(f"{BASE}/delivery", timeout=10)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_delivery_dashboard_contains_html(self, anon):
        r = anon.get(f"{BASE}/delivery", timeout=10)
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_get_deliveries_api(self, anon):
        r = anon.get(f"{BASE}/api/deliveries", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert isinstance(data.get("data"), list)


class TestDeliveryAssignments:

    def _unique_order_id(self):
        return f"TEST-{uuid.uuid4().hex[:8].upper()}"

    def test_create_assignment_valid(self, anon):
        order_id = self._unique_order_id()
        payload = {**DELIVERY_PAYLOAD, "order_id": order_id}
        r = anon.post(f"{BASE}/api/delivery/assignments", json=payload, timeout=10)
        assert r.status_code == 201
        data = r.json()
        assert data.get("status") == "success"
        assert data["data"]["delivery"]["order_id"] == order_id

    def test_create_assignment_missing_order_id(self, anon):
        payload = {k: v for k, v in DELIVERY_PAYLOAD.items() if k != "order_id"}
        r = anon.post(f"{BASE}/api/delivery/assignments", json=payload, timeout=10)
        assert r.status_code == 400
        data = r.json()
        assert data.get("status") == "error"
        assert "MISSING_FIELDS" in str(data.get("error", {}).get("code", ""))

    def test_create_assignment_missing_address(self, anon):
        payload = {k: v for k, v in DELIVERY_PAYLOAD.items() if k != "address"}
        payload["order_id"] = self._unique_order_id()
        r = anon.post(f"{BASE}/api/delivery/assignments", json=payload, timeout=10)
        assert r.status_code == 400
        assert "MISSING_FIELDS" in str(r.json().get("error", {}).get("code", ""))

    def test_create_assignment_no_body(self, anon):
        r = anon.post(f"{BASE}/api/delivery/assignments", json={}, timeout=10)
        assert r.status_code == 400

    def test_delivery_details_found(self, anon):
        order_id = self._unique_order_id()
        anon.post(f"{BASE}/api/delivery/assignments",
                  json={**DELIVERY_PAYLOAD, "order_id": order_id}, timeout=10)
        r = anon.get(f"{BASE}/delivery/{order_id}", timeout=10)
        assert r.status_code == 200

    def test_delivery_details_not_found(self, anon):
        r = anon.get(f"{BASE}/delivery/ORDER-DOES-NOT-EXIST-99999", timeout=10)
        assert r.status_code == 404
        assert "error" in r.json()

    def test_update_delivery_status(self, anon):
        order_id = self._unique_order_id()
        anon.post(f"{BASE}/api/delivery/assignments",
                  json={**DELIVERY_PAYLOAD, "order_id": order_id}, timeout=10)
        r = anon.post(
            f"{BASE}/api/delivery/status",
            json={"order_id": order_id, "status": "En Route"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert data["data"]["delivery"]["status"] == "En Route"

    def test_update_delivery_status_not_found(self, anon):
        r = anon.post(
            f"{BASE}/api/delivery/status",
            json={"order_id": "NONEXISTENT-ORDER-XYZ", "status": "En Route"},
            timeout=10,
        )
        assert r.status_code == 404
        assert r.json().get("status") == "error"

    def test_complete_delivery(self, anon):
        order_id = self._unique_order_id()
        anon.post(f"{BASE}/api/delivery/assignments",
                  json={**DELIVERY_PAYLOAD, "order_id": order_id}, timeout=10)
        r = anon.post(
            f"{BASE}/api/delivery/complete",
            json={"order_id": order_id},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert data["data"]["delivery"]["status"] == "Delivered"

    def test_complete_delivery_not_found(self, anon):
        r = anon.post(
            f"{BASE}/api/delivery/complete",
            json={"order_id": "NONEXISTENT-ORDER-XYZ"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_delivery_status_persists_across_requests(self, anon):
        """Verify in-memory store retains entries between requests."""
        order_id = self._unique_order_id()
        anon.post(f"{BASE}/api/delivery/assignments",
                  json={**DELIVERY_PAYLOAD, "order_id": order_id}, timeout=10)
        # Fetch all deliveries and confirm the new entry appears
        r = anon.get(f"{BASE}/api/deliveries", timeout=10)
        ids = [d["order_id"] for d in r.json().get("data", [])]
        assert order_id in ids


# ===========================================================================
# 8. Restock Pipeline
# ===========================================================================

class TestRestock:

    def test_restock_returns_valid_structure(self, anon):
        r = anon.post(f"{BASE}/api/restock", timeout=120)
        assert r.status_code in (200, 207, 502, 503), f"Unexpected: {r.status_code}"
        if r.status_code in (200, 207, 502):
            data = r.json()
            # All required keys must be present
            for key in ("checked", "low_stock", "restocked", "skipped", "failed", "actions"):
                assert key in data, f"Missing key '{key}' in restock response: {data}"
            # Numeric fields must be non-negative integers
            for key in ("checked", "low_stock", "restocked", "skipped", "failed"):
                assert isinstance(data[key], int), f"'{key}' is not an int"
                assert data[key] >= 0, f"'{key}' is negative"
            # actions must be a list
            assert isinstance(data["actions"], list)

    def test_restock_502_has_error_structure(self, anon):
        """
        If every restock attempt fails CIS returns 502.
        The body must still be the summary dict (not an unstructured error).
        """
        r = anon.post(f"{BASE}/api/restock", timeout=120)
        if r.status_code == 502:
            data = r.json()
            assert "failed" in data
            assert data["failed"] > 0


# ===========================================================================
# 9. Legacy pass-through routes (/orders/request, /orders/ship)
# ===========================================================================

class TestLegacyOrderRoutes:

    def test_orders_request_missing_items(self, anon):
        r = anon.post(f"{BASE}/orders/request", json={}, timeout=15)
        assert r.status_code == 400
        assert "items" in r.json().get("error", "")

    def test_orders_request_empty_items(self, anon):
        r = anon.post(f"{BASE}/orders/request", json={"items": []}, timeout=15)
        assert r.status_code == 400

    def test_orders_request_valid_returns_200_or_error(self, anon):
        """
        CIS may accept the lock or return 409/503.
        We just verify the route is wired up correctly.
        """
        r = anon.post(
            f"{BASE}/orders/request",
            json={"items": [{"product_id": "PROD-CARROTS", "quantity": 1}]},
            timeout=30,
        )
        assert r.status_code in (200, 400, 401, 409, 503)

    def test_orders_ship_missing_order_id(self, anon):
        r = anon.post(f"{BASE}/orders/ship", json={}, timeout=15)
        assert r.status_code == 400
        assert "order_id" in r.json().get("error", "")

    def test_orders_ship_bogus_order_id(self, anon):
        r = anon.post(
            f"{BASE}/orders/ship",
            json={"order_id": f"BOGUS-{uuid.uuid4().hex}"},
            timeout=30,
        )
        # CIS will reject bogus IDs — 4xx or 503
        assert r.status_code in (400, 401, 404, 409, 410, 503)


# ===========================================================================
# 10. Auth callback route (/auth/cs)
# ===========================================================================

class TestAuthCS:

    def test_auth_cs_no_token_redirects_to_login(self, anon):
        r = anon.get(f"{BASE}/auth/cs", allow_redirects=False, timeout=10)
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("Location", "")

    def test_auth_cs_invalid_token_redirects_to_login(self, anon):
        r = anon.get(
            f"{BASE}/auth/cs",
            params={"token": "this.is.not.a.valid.jwt"},
            allow_redirects=False,
            timeout=10,
        )
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("Location", "")
