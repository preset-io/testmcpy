"""
Database session management for testmcpy.

Provides SQLAlchemy engine creation, session factory, and FastAPI dependency.
"""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from testmcpy.models import Base

# Module-level engine and session factory
_engine = None
_SessionLocal = None


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Get the database file path, creating parent dirs if needed.

    Resolution order: explicit argument > TESTMCPY_DB_PATH env var > default (.testmcpy/storage.db)
    """
    if db_path is None:
        db_path = os.environ.get("TESTMCPY_DB_PATH")
    if db_path is None:
        db_dir = Path.cwd() / ".testmcpy"
        db_dir.mkdir(exist_ok=True)
        return db_dir / "storage.db"
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_engine(db_path: str | Path | None = None):
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        path = get_db_path(db_path)
        url = f"sqlite:///{path}"
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def get_session_factory(db_path: str | Path | None = None) -> sessionmaker:
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(db_path)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def init_db(db_path: str | Path | None = None) -> None:
    """Initialize the database, creating all tables."""
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)


def get_db(db_path: str | Path | None = None) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    session_factory = get_session_factory(db_path)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Reset the engine and session factory (useful for testing)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
