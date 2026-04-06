import os
import requests


def test_secret_endpoint_system():
    base_url = os.getenv("SYSTEM_TEST_BASE_URL", "http://127.0.0.1:5000")
    response = requests.get(f"{base_url}/secret", timeout=5)

    assert response.status_code == 200

    data = response.json()
    assert "secret" in data
    assert isinstance(data["secret"], str)
    assert len(data["secret"]) > 0
