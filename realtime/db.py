from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pandas as pd

from realtime.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def read_df(sql: str, **params) -> pd.DataFrame:
    """Execute a read-only parameterised query and return a pandas DataFrame.

    Uses SQLAlchemy 2.0 connection API. Named params are passed as :name in SQL.
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)
