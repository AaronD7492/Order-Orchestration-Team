import psycopg2
from src.config import Config


def get_db_connection():
    return psycopg2.connect(
        host=Config.db_host(),
        port=Config.db_port(),
        dbname=Config.db_name(),
        user=Config.db_user(),
        password=Config.db_password()
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
            cursor.execute(query, (Config.team_name(),))
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"No secret found for team '{Config.team_name()}'")

            return row[0]
    finally:
        conn.close()