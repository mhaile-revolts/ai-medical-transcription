from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Iterator, Protocol

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class SessionProtocol(Protocol):  # pragma: no cover - placeholder for real ORM session
    """Minimal protocol for a DB session used by repository implementations.

    This is intentionally tiny so that we can plug in a concrete ORM (e.g.,
    SQLAlchemy) later without changing higher-level code.
    """

    def __enter__(self) -> "SessionProtocol": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...


SessionFactory = Callable[[], SessionProtocol]


def create_sqlalchemy_session_factory(database_url: str) -> SessionFactory:
    """Create a SQLAlchemy-backed SessionFactory.

    This helper is optional and not wired into the application yet. It provides
    a straightforward way to build a factory that produces SQLAlchemy Session
    instances compatible with SessionProtocol.
    """

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)

    def _factory() -> SessionProtocol:  # pragma: no cover - thin wrapper
        return SessionLocal()  # type: ignore[return-value]

    return _factory


@contextmanager
def dummy_session_factory() -> Iterator[SessionProtocol]:  # pragma: no cover - dev placeholder
    """Development stub session factory.

    Real deployments should replace this with a factory that yields actual ORM
    sessions. This stub exists so that Sql*Repository skeletons can be
    type-checked without introducing a hard dependency on any specific ORM.
    """

    # In a real implementation, yield a live DB session here.
    raise RuntimeError("dummy_session_factory should be replaced with a real implementation")
    yield  # type: ignore[misc]
