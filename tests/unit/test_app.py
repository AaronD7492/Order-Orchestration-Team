from unittest.mock import patch
from src.app import create_app


@patch("src.app.get_team_secret")
def test_secret_endpoint_returns_secret_json(mock_get_team_secret):
    mock_get_team_secret.return_value = "ORDER_SECRET_123"

    app = create_app()
    client = app.test_client()

    response = client.get("/secret")

    assert response.status_code == 200
    assert response.get_json() == {"secret": "ORDER_SECRET_123"}
