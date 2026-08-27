import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def usgs_crudo() -> bytes:
    return (FIXTURES / "usgs_all_day.geojson").read_bytes()


@pytest.fixture
def gdacs_crudo() -> bytes:
    return (FIXTURES / "gdacs_rss.xml").read_bytes()


@pytest.fixture
def eonet_crudo() -> bytes:
    return (FIXTURES / "eonet_events.json").read_bytes()


@pytest.fixture
def ahora() -> datetime:
    """Instante fijo, coherente con las fechas de los fixtures."""
    return datetime(2026, 8, 6, 2, 0, 0, tzinfo=timezone.utc)
