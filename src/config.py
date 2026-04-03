import os


class Config:
    @staticmethod
    def db_host():
        return os.getenv("DB_HOST", "localhost")

    @staticmethod
    def db_port():
        return os.getenv("DB_PORT", "5432")

    @staticmethod
    def db_name():
        return os.getenv("DB_NAME", "postgres")

    @staticmethod
    def db_user():
        return os.getenv("DB_USER", "postgres")

    @staticmethod
    def db_password():
        return os.getenv("DB_PASSWORD", "postgres")

    @staticmethod
    def team_name():
        return os.getenv("TEAM_NAME", "Order Orchestration")