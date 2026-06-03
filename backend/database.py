"""Configuration de la base de données SQLAlchemy (SQLite local / PostgreSQL Supabase)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL

# PostgreSQL n'accepte pas check_same_thread (SQLite only)
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    __allow_unmapped__ = True


def get_db():
    """Retourne une session BDD."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
