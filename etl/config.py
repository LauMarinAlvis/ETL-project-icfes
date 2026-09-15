import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Busca el .env en la raíz del proyecto (un nivel arriba de src/)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "etl_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "etl_password")
DB_NAME = os.getenv("DB_NAME", "saber11_dw")


def get_engine(echo: bool = False) -> Engine:
    """Crea (y valida con un ping) el engine de SQLAlchemy hacia MySQL."""
    url = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    return create_engine(url, echo=echo, pool_pre_ping=True)