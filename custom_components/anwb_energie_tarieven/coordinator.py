"""Data update coordinator for ANWB Energie."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TIMEZONE,
    AnwbEnergieClient,
    AnwbEnergieError,
    PricePoint,
    is_day_complete,
    price_at,
)
from .const import (
    COMMODITIES,
    COMMODITY_ELECTRICITY,
    DOMAIN,
    FAILURE_RETRY_INTERVAL,
    PUBLISH_WINDOW_END,
    PUBLISH_WINDOW_START,
    RETRY_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type AnwbEnergieData = dict[str, list[PricePoint]]
type AnwbEnergieConfigEntry = ConfigEntry[AnwbEnergieCoordinator]


class AnwbEnergieCoordinator(DataUpdateCoordinator[AnwbEnergieData]):
    """Fetches electricity and gas prices for yesterday up to and including tomorrow."""

    config_entry: AnwbEnergieConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AnwbEnergieConfigEntry,
        client: AnwbEnergieClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._fetch_failing = False

    async def _async_update_data(self) -> AnwbEnergieData:
        today = datetime.now(TIMEZONE).date()
        start = datetime.combine(today - timedelta(days=1), time(), TIMEZONE)
        end = datetime.combine(today + timedelta(days=2), time(), TIMEZONE)

        data: AnwbEnergieData = {}
        error: AnwbEnergieError | None = None
        for commodity in COMMODITIES:
            try:
                data[commodity] = await self.client.async_get_prices(
                    commodity, start, end
                )
            except AnwbEnergieError as err:
                error = err
        if error is not None:
            return self._keep_last_prices(data, error)

        if self._fetch_failing:
            _LOGGER.info("Fetching tariffs recovered")
            self._fetch_failing = False
        self.update_interval = self._next_interval(data)
        return data

    def _keep_last_prices(
        self, fetched: AnwbEnergieData, err: AnwbEnergieError
    ) -> AnwbEnergieData:
        """Use the last prices for what failed while the API is unreachable.

        The prices cover yesterday up to and including tomorrow, so they stay
        valid through a short outage. The update fails when there are no earlier
        prices (Home Assistant then retries the setup) or once they no longer cover
        the current hour (the sensors then become unavailable).
        """
        self.update_interval = FAILURE_RETRY_INTERVAL
        if self.data is None:
            raise UpdateFailed(str(err)) from err
        data = {**self.data, **fetched}
        current = price_at(data[COMMODITY_ELECTRICITY], datetime.now(TIMEZONE))
        if current is None or current.all_in is None:
            raise UpdateFailed(f"{err}; the last prices are out of date") from err

        if not self._fetch_failing:
            _LOGGER.warning(
                "%s; keeping the last prices and retrying every %s",
                err,
                FAILURE_RETRY_INTERVAL,
            )
            self._fetch_failing = True
        return data

    def _next_interval(self, data: AnwbEnergieData) -> timedelta:
        """Poll more often while tomorrow's electricity prices are still missing.

        Gas is not part of this check: its gas day starts at 06:00 and is published
        on a different schedule, so the regular hourly update covers it.
        """
        now = datetime.now(TIMEZONE)
        tomorrow = now.date() + timedelta(days=1)
        if is_day_complete(data[COMMODITY_ELECTRICITY], tomorrow):
            return UPDATE_INTERVAL

        window_start = datetime.combine(now.date(), PUBLISH_WINDOW_START, TIMEZONE)
        window_end = datetime.combine(now.date(), PUBLISH_WINDOW_END, TIMEZONE)
        if window_start <= now < window_end:
            return RETRY_INTERVAL
        if now < window_start:
            return min(UPDATE_INTERVAL, window_start - now)
        return UPDATE_INTERVAL
