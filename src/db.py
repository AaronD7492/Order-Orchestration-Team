import psycopg2
from src.config import Config


def get_db_connection():
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD
    )


def get_team_secret():
    query = """
        SELECT secret
        FROM dtsecrets
        WHERE teamname = %s
        LIMIT 1
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (Config.TEAM_NAME,))
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"No secret found for team '{Config.TEAM_NAME}'")

            return row[0]
    finally:
        conn.close()
