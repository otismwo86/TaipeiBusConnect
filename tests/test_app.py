from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app import app,get_current_table,create_jwt_token
import jwt
from datetime import datetime, timedelta, timezone

client = TestClient(app)

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>台北BusConnect - 搜尋</title>" in response.text

def test_search_bus():
    route_name = "232"

    expected_results = [
        {"stop_name": "Stop 1", "position_lon": 121.5645, "position_lat": 25.0326, "direction": 0},
        {"stop_name": "Stop 2", "position_lon": 121.5650, "position_lat": 25.0328, "direction": 0}
    ]

    with patch("app.connect_to_db") as mock_connect:
        mock_db_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db_connection
        mock_db_connection.cursor.return_value = mock_cursor

        mock_cursor.execute.return_value = None

        mock_cursor.fetchall.return_value = expected_results

        response = client.get(f"/api/searchlocation?route_name={route_name}")

        assert response.status_code == 200

        assert response.json() == expected_results


def test_get_current_table():
    with patch("app.connect_to_db") as mock_connect:

        mock_db_connection = MagicMock()
        mock_cursor = MagicMock()

        mock_connect.return_value = mock_db_connection

        mock_db_connection.cursor.return_value = mock_cursor

        mock_cursor.execute.return_value = None

        mock_cursor.fetchone.return_value = ("bus_estimated_table",)

        result = get_current_table()

        assert result == "bus_estimated_table"

        mock_cursor.execute.assert_called_once_with("SELECT current_table FROM table_status")

        mock_cursor.close.assert_called_once()
        mock_db_connection.close.assert_called_once()

def test_get_current_table_no_result():
    with patch("app.connect_to_db") as mock_connect:
        mock_db_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_db_connection
        mock_db_connection.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None

        result = get_current_table()

        assert result == "bus_estimated"

        mock_cursor.close.assert_called_once()
        mock_db_connection.close.assert_called_once()

def test_create_jwt_token():
    user_id = 123
    name = "Test User"
    email = "test@example.com"
    fake_secret_key = "fake_secret"
    with patch("app.SECRET_KEY", fake_secret_key):
        with patch("app.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            token = create_jwt_token(user_id, name , email)
            decoded_token = jwt.decode(token, fake_secret_key, algorithms=["HS256"])
            assert decoded_token["sub"] == user_id
            assert decoded_token["name"] == name
            assert decoded_token["email"] == email
            expected_expire_time = datetime(2025, 1, 4, 12, 0, 0, tzinfo=timezone.utc)
            assert decoded_token["exp"] == int(expected_expire_time.timestamp())
            header = jwt.get_unverified_header(token)
            assert header["alg"] == "HS256"
