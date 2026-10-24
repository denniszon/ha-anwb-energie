"""Tests for the API parsing helpers (no Home Assistant needed)."""

from datetime import date, datetime
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

# Load api.py directly: the package __init__ imports homeassistant.
_spec = importlib.util.spec_from_file_location(
    "anwb_energie_api", ROOT / "custom_components" / "anwb_energie" / "api.py"
)
api = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = api
_spec.loader.exec_module(api)

TZ = api.TIMEZONE
DST_DAY = date(2026, 10, 25)


@pytest.fixture
def electricity() -> list:
    return api.parse_prices(json.loads((FIXTURES / "electricity_dst.json").read_text()))


@pytest.fixture
def gas() -> list:
    return api.parse_prices(json.loads((FIXTURES / "gas_dst.json").read_text()))


def test_cents_are_converted_to_euro(electricity: list) -> None:
    point = api.price_at(electricity, datetime(2026, 10, 25, 18, 30, tzinfo=TZ))
    assert point.all_in == 0.29
    assert point.market == 0.16


def test_dst_day_has_25_hours(electricity: list) -> None:
    points = api.prices_for_day(electricity, DST_DAY)
    assert len(points) == 25
    # The two 02:00 hours are different moments.
    two_oclock = [p for p in points if p.start.astimezone(TZ).hour == 2]
    assert len(two_oclock) == 2
    assert two_oclock[0].end == two_oclock[1].start


def test_price_after_dst_change_is_not_shifted(electricity: list) -> None:
    point = api.price_at(electricity, datetime(2026, 10, 25, 14, 15, tzinfo=TZ))
    assert point.start == datetime.fromisoformat("2026-10-25T14:00:00+01:00")
    assert point.all_in == 0.13


def test_unpublished_hours_are_none(electricity: list) -> None:
    tomorrow = api.prices_for_day(electricity, date(2026, 10, 26))
    assert tomorrow
    assert all(p.all_in is None and p.market is None for p in tomorrow)
    assert api.is_day_complete(electricity, DST_DAY)
    assert not api.is_day_complete(electricity, date(2026, 10, 26))


def test_missing_day_is_not_complete(electricity: list) -> None:
    assert not api.is_day_complete(electricity, date(2026, 10, 30))


def test_gas_prices(gas: list) -> None:
    points = api.prices_for_day(gas, DST_DAY)
    assert len(points) == 25
    # The gas day starts at 06:00; the next one was not yet published in the fixture.
    point = api.price_at(gas, datetime(2026, 10, 25, 5, 30, tzinfo=TZ))
    assert point.all_in == 1.91
    assert point.market == 1.1
    assert api.price_at(gas, datetime(2026, 10, 25, 6, 30, tzinfo=TZ)).all_in is None


def test_price_type_selection() -> None:
    point = api.PricePoint(
        start=datetime(2026, 1, 1, tzinfo=TZ), all_in=0.25, market=0.1
    )
    assert point.price("all_in") == 0.25
    assert point.price("market") == 0.1


def test_format_date_uses_utc() -> None:
    start = datetime(2026, 10, 25, 0, 0, tzinfo=TZ)
    assert api._format_date(start) == "2026-10-24T22:00:00.000Z"
