import os
import time
import psycopg2
from src.app import create_app


def wait_for_db():
    for _ in range(10):
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                dbname=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
            )
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(2)
    raise RuntimeError("Database not ready in time")


def test_secret_endpoint_returns_secret_from_database():
    wait_for_db()

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dtsecrets (
                    teamname TEXT PRIMARY KEY,
                    secret TEXT NOT NULL
                )
            """)
            cursor.execute("DELETE FROM dtsecrets WHERE teamname = %s", ("Integration Team",))
            cursor.execute(
                "INSERT INTO dtsecrets (teamname, secret) VALUES (%s, %s)",
                ("Integration Team", "integrationSecret123")
            )
            conn.commit()
    finally:
        conn.close()

    os.environ["TEAM_NAME"] = "Integration Team"

    app = create_app()
    client = app.test_client()
    response = client.get("/secret")

    assert response.status_code == 200
    assert response.get_json() == {"secret": "integrationSecret123"}