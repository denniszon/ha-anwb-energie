"""Client for the (unofficial) ANWB Energie tariff API.

This module deliberately has no Home Assistant imports, so it can be tested
standalone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

API_URL = "https://api.anwb.nl/energy/energy-services/v3/tarieven/{commodity}"
TIMEZONE = ZoneInfo("Europe/Amsterdam")
INTERVAL = timedelta(hours=1)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class AnwbEnergieError(Exception):
    """Raised when the tariffs could not be retrieved."""


@dataclass(frozen=True)
class PricePoint:
    """Price for one hour, in euro."""

    start: datetime
    all_in: float | None
    market: float | None

    @property
    def end(self) -> datetime:
        """End of the hour."""
        return self.start + INTERVAL

    def price(self, price_type: str) -> float | None:
        """Return the price for `all_in` or `market`."""
        return self.all_in if price_type == "all_in" else self.market


def parse_prices(payload: dict[str, Any]) -> list[PricePoint]:
    """Convert an API response (prices in cents) to price points in euro."""
    points = []
    for item in payload.get("data", []):
        values = item.get("values") or {}
        points.append(
            PricePoint(
                start=datetime.fromisoformat(item["date"]),
                all_in=_cents_to_euro(values.get("allInPrijs")),
                market=_cents_to_euro(values.get("marktprijs")),
            )
        )
    return sorted(points, key=lambda point: point.start)


def prices_for_day(points: list[PricePoint], day: date) -> list[PricePoint]:
    """Return the price points that start on the given day (Amsterdam time)."""
    return [point for point in points if point.start.astimezone(TIMEZONE).date() == day]


def price_at(points: list[PricePoint], moment: datetime) -> PricePoint | None:
    """Return the price point that covers the given moment."""
    for point in points:
        if point.start <= moment < point.end:
            return point
    return None


def is_day_complete(points: list[PricePoint], day: date) -> bool:
    """Return True when all prices for the given day are published."""
    day_points = prices_for_day(points, day)
    return bool(day_points) and all(
        point.all_in is not None and point.market is not None for point in day_points
    )


def _cents_to_euro(value: float | None) -> float | None:
    return None if value is None else round(value / 100, 4)


def _format_date(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class AnwbEnergieClient:
    """Fetches hourly electricity and gas tariffs."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._session = session

    async def async_get_prices(
        self, commodity: str, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """Return hourly prices for `electricity` or `gas` between start and end."""
        params = {
            "startDate": _format_date(start),
            "endDate": _format_date(end),
            "interval": "HOUR",
        }
        try:
            async with self._session.get(
                API_URL.format(commodity=commodity),
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AnwbEnergieError(
                f"Error fetching {commodity} tariffs: {err}"
            ) from err

        try:
            return parse_prices(payload)
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            raise AnwbEnergieError(
                f"Unexpected {commodity} tariff response: {err}"
            ) from err
