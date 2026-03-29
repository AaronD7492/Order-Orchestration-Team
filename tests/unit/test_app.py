from unittest.mock import patch
from src.app import create_app
from src.cis_client import InsufficientStockError, LockExpiredError, CISError


@patch("src.app.get_team_secret")
def test_secret_endpoint_returns_secret_json(mock_get_team_secret):
    mock_get_team_secret.return_value = "ORDER_SECRET_123"

    app = create_app()
    client = app.test_client()

    response = client.get("/secret")

    assert response.status_code == 200
    assert response.get_json() == {"secret": "ORDER_SECRET_123"}


# --- POST /orders/request ---

@patch("src.app.lock_inventory")
def test_orders_request_success(mock_lock):
    mock_lock.return_value = {"order_id": "abc123", "status": "locked"}

    client = create_app().test_client()
    response = client.post(
        "/orders/request",
        json={"items": [{"product_id": "p1", "quantity": 2}]}
    )

    assert response.status_code == 200
    assert response.get_json()["order_id"] == "abc123"
    mock_lock.assert_called_once_with([{"product_id": "p1", "quantity": 2}])


@patch("src.app.lock_inventory")
def test_orders_request_insufficient_stock(mock_lock):
    mock_lock.side_effect = InsufficientStockError("Insufficient stock", 409)

    client = create_app().test_client()
    response = client.post(
        "/orders/request",
        json={"items": [{"product_id": "p1", "quantity": 999}]}
    )

    assert response.status_code == 409
    assert "Insufficient stock" in response.get_json()["error"]


@patch("src.app.lock_inventory")
def test_orders_request_cis_unavailable(mock_lock):
    mock_lock.side_effect = CISError("CIS unreachable: connection refused", 503)

    client = create_app().test_client()
    response = client.post(
        "/orders/request",
        json={"items": [{"product_id": "p1", "quantity": 1}]}
    )

    assert response.status_code == 503


def test_orders_request_missing_items():
    client = create_app().test_client()
    response = client.post("/orders/request", json={})

    assert response.status_code == 400
    assert "items" in response.get_json()["error"]


def test_orders_request_empty_items():
    client = create_app().test_client()
    response = client.post("/orders/request", json={"items": []})

    assert response.status_code == 400


# --- POST /orders/ship ---

@patch("src.app.ship_order")
def test_orders_ship_success(mock_ship):
    mock_ship.return_value = {"order_id": "abc123", "status": "shipped"}

    client = create_app().test_client()
    response = client.post("/orders/ship", json={"order_id": "abc123"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "shipped"
    mock_ship.assert_called_once_with("abc123")


@patch("src.app.ship_order")
def test_orders_ship_lock_expired(mock_ship):
    mock_ship.side_effect = LockExpiredError("Lock expired", 410)

    client = create_app().test_client()
    response = client.post("/orders/ship", json={"order_id": "abc123"})

    assert response.status_code == 410
    assert "Lock expired" in response.get_json()["error"]


@patch("src.app.ship_order")
def test_orders_ship_cis_unavailable(mock_ship):
    mock_ship.side_effect = CISError("CIS unreachable", 503)

    client = create_app().test_client()
    response = client.post("/orders/ship", json={"order_id": "abc123"})

    assert response.status_code == 503


def test_orders_ship_missing_order_id():
    client = create_app().test_client()
    response = client.post("/orders/ship", json={})

    assert response.status_code == 400
    assert "order_id" in response.get_json()["error"]
