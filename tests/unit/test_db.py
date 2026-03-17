from unittest.mock import MagicMock, patch
from src.db import get_team_secret


@patch("src.db.get_db_connection")
def test_get_team_secret_from_database(mock_get_db_connection):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = ("ORDER_SECRET_123",)

    result = get_team_secret()

    assert result == "ORDER_SECRET_123"
    mock_cursor.execute.assert_called_once()
    mock_cursor.fetchone.assert_called_once()
    mock_conn.close.assert_called_once()
