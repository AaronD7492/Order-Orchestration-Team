from unittest.mock import patch
from src.app import create_app
from src.cis_client import InsufficientStockError, LockExpiredError, CISError


# ---------------------------------------------------------------------------
# GET /secret
# ---------------------------------------------------------------------------

@patch("src.app.get_team_secret")
def test_secret_endpoint_returns_secret_json(mock_get_team_secret):
    mock_get_team_secret.return_value = "ORDER_SECRET_123"

    app = create_app()
    client = app.test_client()

    response = client.get("/secret")

    assert response.status_code == 200
    assert response.get_json() == {"secret": "ORDER_SECRET_123"}


# ---------------------------------------------------------------------------
# POST /checkout/initiate
# ---------------------------------------------------------------------------

def test_checkout_initiate_success():
    client = create_app().test_client()
    response = client.post(
        "/checkout/initiate",
        json={
            "items": [
                {"productId": "PROD-CARROTS", "productName": "Carrots",
                 "quantity": 2.0, "unit": "kg"}
            ],
            "userToken": "test-jwt-token",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["redirect_url"] == "/checkout"


def test_checkout_initiate_missing_items():
    client = create_app().test_client()
    response = client.post("/checkout/initiate", json={"userToken": "tok"})
    assert response.status_code == 400
    assert "items" in response.get_json()["error"]


def test_checkout_initiate_empty_items():
    client = create_app().test_client()
    response = client.post("/checkout/initiate", json={"items": []})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /checkout
# ---------------------------------------------------------------------------

def test_checkout_get_no_cart_returns_400():
    client = create_app().test_client()
    response = client.get("/checkout")
    assert response.status_code == 400
    assert "No cart found" in response.get_json()["error"]


def test_checkout_get_returns_cart_and_prefill():
    app = create_app()
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["cart_items"] = [
            {"productId": "PROD-CARROTS", "productName": "Carrots",
             "quantity": 2.0, "unit": "kg"}
        ]

    response = client.get("/checkout")
    assert response.status_code == 200
    data = response.get_json()
    assert "cart_items" in data
    assert "prefill" in data
    assert data["cart_items"][0]["productId"] == "PROD-CARROTS"


# ---------------------------------------------------------------------------
# POST /checkout/submit
# ---------------------------------------------------------------------------

def _initiate_cart(client):
    """Helper: seed a cart into the session via /checkout/initiate."""
    client.post(
        "/checkout/initiate",
        json={
            "items": [
                {"productId": "PROD-CARROTS", "productName": "Carrots",
                 "quantity": 2.0, "unit": "kg", "category": "Produce"}
            ],
            "userToken": None,
        },
    )


@patch("src.app.ship_locked_order")
@patch("src.app.request_order_lock")
@patch("src.app.submit_delivery")
def test_checkout_submit_success(mock_delivery, mock_lock, mock_ship):
    mock_lock.return_value = {"lockOrderId": "LOCK-1", "lockToken": "TOK-1"}
    mock_ship.return_value = {"shippingId": "SHIP-1", "f2fOrderId": "F2F-1"}

    app = create_app()
    client = app.test_client()
    _initiate_cart(client)

    response = client.post(
        "/checkout/submit",
        json={
            "addressLine1": "100 King St",
            "city": "Waterloo",
            "province": "ON",
            "postalCode": "N2L 3G1",
            "dropOff": True,
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "f2fOrderId" in data
    assert data["shippingId"] == "SHIP-1"


@patch("src.app.request_order_lock")
def test_checkout_submit_out_of_stock(mock_lock):
    mock_lock.side_effect = InsufficientStockError("Not enough stock", 409)

    app = create_app()
    client = app.test_client()
    _initiate_cart(client)

    response = client.post(
        "/checkout/submit",
        json={"addressLine1": "100 King St", "city": "Waterloo", "province": "ON"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "out_of_stock"


@patch("src.app.request_order_lock")
def test_checkout_submit_cis_unavailable(mock_lock):
    mock_lock.side_effect = CISError("CIS unreachable", 503)

    app = create_app()
    client = app.test_client()
    _initiate_cart(client)

    response = client.post(
        "/checkout/submit",
        json={"addressLine1": "100 King St", "city": "Waterloo", "province": "ON"},
    )
    assert response.status_code == 503
    assert response.get_json()["error"] == "cis_error"


@patch("src.app.ship_locked_order")
@patch("src.app.request_order_lock")
def test_checkout_submit_lock_expired(mock_lock, mock_ship):
    mock_lock.return_value = {"lockOrderId": "LOCK-1", "lockToken": "TOK-1"}
    mock_ship.side_effect = LockExpiredError("Lock expired", 409)

    app = create_app()
    client = app.test_client()
    _initiate_cart(client)

    response = client.post(
        "/checkout/submit",
        json={"addressLine1": "100 King St", "city": "Waterloo", "province": "ON"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "lock_expired"


def test_checkout_submit_missing_required_fields():
    client = create_app().test_client()
    response = client.post("/checkout/submit", json={"city": "Waterloo", "province": "ON"})
    assert response.status_code == 400
    assert "addressLine1" in response.get_json()["error"]


def test_checkout_submit_no_cart():
    client = create_app().test_client()
    response = client.post(
        "/checkout/submit",
        json={"addressLine1": "100 King St", "city": "Waterloo", "province": "ON"},
    )
    assert response.status_code == 400
    assert "No cart found" in response.get_json()["error"]
