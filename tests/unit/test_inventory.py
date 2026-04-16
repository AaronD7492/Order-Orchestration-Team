import pytest
from unittest.mock import patch

from src.app import create_app
from src.cis_client import CISError


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@patch("src.app.get_pooled_inventory")
def test_inventory_success(mock_cis, client):

    mock_cis.return_value = {
        "page": 1,
        "pageSize": 10,
        "total": 2,
        "hasNext": False,
        "items": [
            {
                "productId": "PROD-1",
                "productName": "Apples",
                "hierarchy": ["Produce"],
                "quantityOnHand": 100,
                "unit": "kg"
            },
            {
                "productId": "PROD-2",
                "productName": "Milk",
                "hierarchy": ["Dairy"],
                "quantityOnHand": 50,
                "unit": "l"
            }
        ]
    }

    response = client.get("/inventory/pooled?page=1&pageSize=10")

    assert response.status_code == 200

    mock_cis.assert_called_once_with(1, 10)  # 👈 add this

    data = response.get_json()
    assert data["total"] == 2


def test_inventory_invalid_page(client):
    response = client.get("/inventory/pooled?page=0&pageSize=10")

    assert response.status_code == 400
    assert "page must be >= 1" in response.get_json()["error"]


def test_inventory_invalid_page_size(client):
    response = client.get("/inventory/pooled?page=1&pageSize=999")

    assert response.status_code == 400
    assert "pageSize must be between 1 and 500" in response.get_json()["error"]


@patch("src.app.get_pooled_inventory")
def test_inventory_cis_error(mock_cis, client):

    mock_cis.side_effect = CISError("CIS down", 503)

    response = client.get("/inventory/pooled?page=1&pageSize=10")

    assert response.status_code == 503
    data = response.get_json()
    assert data["error"] == "cis_error"
    assert "CIS down" in data["message"]


def test_inventory_invalid_type(client):
    response = client.get("/inventory/pooled?page=abc&pageSize=10")

    assert response.status_code == 400
    assert "must be integers" in response.get_json()["error"]
