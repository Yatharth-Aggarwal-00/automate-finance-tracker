import os

# Point the app at the test database and disable the LLM *before* app modules load.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://finance:finance@localhost:5433/finance_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ANTHROPIC_API_KEY"] = ""

from datetime import date, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, Base, Instrument, PriceBar  # noqa: E402


def make_settings(**overrides) -> Settings:
    base = {
        "database_url": TEST_DATABASE_URL,
        "anthropic_api_key": None,
        "paper_fee_percent": Decimal("0.10"),
        "paper_fee_flat": Decimal("0.00"),
    }
    return Settings(_env_file=None, **(base | overrides))


@pytest.fixture(scope="session")
def schema():
    """Created lazily, so pure unit tests run without a database."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db(schema):
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def add_instrument(db: Session, symbol: str, closes: list[str], sector: str = "Information Technology",
                   end: date = date(2026, 10, 23)) -> Instrument:
    """Insert an instrument with one daily bar per close, ending on `end`."""
    inst = Instrument(symbol=symbol, name=f"{symbol} Ltd", exchange="NSE", sector=sector,
                      data_source="test", data_status="SIMULATED")
    db.add(inst)
    db.flush()
    start = end - timedelta(days=len(closes) - 1)
    for i, c in enumerate(closes):
        p = Decimal(c)
        db.add(PriceBar(instrument_id=inst.id, date=start + timedelta(days=i), open=p, high=p, low=p, close=p, volume=1000))
    db.commit()
    return inst


def add_account(db: Session, cash: str = "100000.00") -> Account:
    acct = Account(name="Test", initial_cash=Decimal(cash), cash=Decimal(cash))
    db.add(acct)
    db.commit()
    return acct


@pytest.fixture
def market(db):
    """Two IT stocks and one bank with 60 days of steadily rising closes; fresh ₹1,00,000 account."""
    add_instrument(db, "AAA", [str(100 + i) for i in range(60)])  # last close 159
    add_instrument(db, "BBB", [str(1000 + 5 * i) for i in range(60)])  # last close 1295
    add_instrument(db, "CCC", [str(500 - i) for i in range(60)], sector="Financial Services")  # last close 441
    add_account(db)
    return db
