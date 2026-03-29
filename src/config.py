import os


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "postgres")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    TEAM_NAME = os.getenv("TEAM_NAME", "Order Orchestration")
    CIS_BASE_URL = os.getenv("CIS_BASE_URL", "http://138.197.144.135:8201/api/v1")
    CIS_API_KEY = os.getenv("CIS_API_KEY", "")
    ODS_BASE_URL = os.getenv("ODS_BASE_URL", "http://178.128.226.23:8001/api/v1")
    ODS_API_KEY = os.getenv("ODS_API_KEY", "")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
