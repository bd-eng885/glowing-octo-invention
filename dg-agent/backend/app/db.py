from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):  # pragma: no cover - driver hook
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return eng


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Database-level protection for the audit log: rows can be inserted but never
# updated or deleted. Combined with the hash chain this makes tampering evident.
_SQLITE_AUDIT_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;""",
    """CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;""",
]
_PG_AUDIT_TRIGGERS = [
    """CREATE OR REPLACE FUNCTION audit_log_block() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;""",
    "DROP TRIGGER IF EXISTS audit_no_modify ON audit_log;",
    """CREATE TRIGGER audit_no_modify BEFORE UPDATE OR DELETE ON audit_log
       FOR EACH ROW EXECUTE FUNCTION audit_log_block();""",
]


def init_db(eng=None) -> None:
    from . import models  # noqa: F401  (register tables)

    eng = eng or engine
    Base.metadata.create_all(eng)
    stmts = _SQLITE_AUDIT_TRIGGERS if eng.dialect.name == "sqlite" else _PG_AUDIT_TRIGGERS
    with eng.begin() as conn:
        for s in stmts:
            conn.execute(text(s))
