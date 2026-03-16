from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

db_url = settings.database_url
connect_args = {}
try:
    if make_url(db_url).drivername.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
except Exception:
    pass

engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
