import os


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "postgres")
    DB_USER = os.getenv("DB_USER", "orders")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "orchestrate")
    TEAM_NAME = os.getenv("TEAM_NAME", "Order Orchestration")
    CIS_BASE_URL = os.getenv("CIS_BASE_URL", "http://138.197.144.135:8201/api/v1")
    CIS_API_KEY = os.getenv("CIS_API_KEY", "S0MDKZEARVRd-_-ElR6viWycEosPIFNzTlaP8aTQIztJf9vT")
    ODS_BASE_URL = os.getenv("ODS_BASE_URL", "http://178.128.226.23:8001/api/v1")
    ODS_API_KEY = os.getenv("ODS_API_KEY", "kMJIoWBGA_A5xNOLH86NRc2yha_4N8n5u-r_zAmB6BZvDssj")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    CFP_HOST = os.getenv("CFP_HOST", "68.183.203.17")
    CFP_PORT = int(os.getenv("CFP_PORT", "22"))
    CFP_USER = os.getenv("CFP_USER", "sec1")
    CFP_PASSWORD = os.getenv("CFP_PASSWORD", "")
    CFP_CACHE_DIR = os.getenv("CFP_CACHE_DIR", "cfp_cache")
    AGNET_BASE_URL = os.getenv("AGNET_BASE_URL", "http://146.190.243.241:8301/api/v1")
    AGNET_API_KEY = os.getenv("AGNET_API_KEY", "rnmhr3mo3wTDOXixi8BF0lTpA-ziln4knstoj5AcBFkbEZNP")
    CS_BASE_URL = os.getenv("CS_BASE_URL", "http://165.22.230.110:7500")
    CS_JWT_PASS = os.getenv("CS_JWT_PASS", "jwtpass123")
    CS_LOGIN_URL = os.getenv("CS_LOGIN_URL", "http://localhost:7500/login")
    F2F_BASE_URL = os.getenv("F2F_BASE_URL", "http://localhost:5001")
    DE_BASE_URL = os.getenv("DE_BASE_URL", "http://localhost:7600")

    # Method-style accessors used by db.py (team convention)
    @classmethod
    def db_host(cls): return cls.DB_HOST
    @classmethod
    def db_port(cls): return int(cls.DB_PORT)
    @classmethod
    def db_name(cls): return cls.DB_NAME
    @classmethod
    def db_user(cls): return cls.DB_USER
    @classmethod
    def db_password(cls): return cls.DB_PASSWORD
    @classmethod
    def team_name(cls): return cls.TEAM_NAME
