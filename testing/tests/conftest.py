import os
import random
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.api.deps import get_db
from app.db.base import Base
from app.db.models import Role, RoleScope


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--seed",
        action="store",
        default=os.getenv("TEST_SEED", "1337"),
        help="Seed for deterministic test data.",
    )


@pytest.fixture(scope="session", autouse=True)
def ensure_report_dirs():
    os.makedirs("testing/reports/backend", exist_ok=True)
    os.makedirs("testing/reports/frontend", exist_ok=True)
    yield


@pytest.fixture(scope="session")
def test_seed(request: pytest.FixtureRequest) -> int:
    raw = request.config.getoption("--seed")
    try:
        return int(raw)
    except Exception:
        return 1337


@pytest.fixture(scope="session")
def db_engine():
    db_path = os.path.join(tempfile.gettempdir(), f"erp_test_{uuid.uuid4().hex}.db")
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="session")
def SessionLocal(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_db(db_engine):
    # SQLite struggles to DROP tables with FK cycles; temporarily disable FK checks.
    with db_engine.begin() as conn:
        try:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        except Exception:
            pass
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)
        try:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        except Exception:
            pass
    yield


@pytest.fixture(scope="function")
def db_session(SessionLocal):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client(SessionLocal):
    app = create_app()

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


@pytest.fixture(scope="function")
def client_factory(SessionLocal):
    def _factory():
        app = create_app()

        def _get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_db
        return TestClient(app)

    return _factory


@pytest.fixture(scope="function")
def rng(test_seed: int):
    return random.Random(test_seed)


@pytest.fixture(scope="function")
def seed_roles(db_session):
    roles = [
        (RoleScope.PLATFORM, "PLATFORM_ADMIN"),
        (RoleScope.COMPANY, "SUPER_ADMIN"),
        (RoleScope.COMPANY, "MANAGER"),
        (RoleScope.COMPANY, "CASHIER"),
        (RoleScope.COMPANY, "PURCHASE"),
        (RoleScope.COMPANY, "AUDITOR"),
        (RoleScope.COMPANY, "EMPLOYEE"),
    ]
    for scope, code in roles:
        exists = db_session.query(Role).filter(Role.scope == scope, Role.code == code).first()
        if not exists:
            db_session.add(Role(scope=scope, code=code, name=code.replace("_", " ").title(), is_system=True))
    db_session.commit()
