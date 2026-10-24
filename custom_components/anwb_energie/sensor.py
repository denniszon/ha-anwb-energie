"""Price sensors for ANWB Energie."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TIMEZONE, PricePoint, is_day_complete, price_at, prices_for_day
from .const import (
    ATTRIBUTION,
    COMMODITY_ELECTRICITY,
    COMMODITY_GAS,
    DOMAIN,
    PRICE_ALL_IN,
    PRICE_MARKET,
)
from .coordinator import AnwbEnergieConfigEntry, AnwbEnergieCoordinator

ELECTRICITY_UNIT = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
GAS_UNIT = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"


def _today_prices(points: list[PricePoint], price_type: str) -> list[float]:
    today = datetime.now(TIMEZONE).date()
    return [
        price
        for point in prices_for_day(points, today)
        if (price := point.price(price_type)) is not None
    ]


def _current(points: list[PricePoint], price_type: str) -> float | None:
    point = price_at(points, datetime.now(TIMEZONE))
    return point.price(price_type) if point else None


def _lowest(points: list[PricePoint], price_type: str) -> float | None:
    prices = _today_prices(points, price_type)
    return min(prices) if prices else None


def _average(points: list[PricePoint], price_type: str) -> float | None:
    prices = _today_prices(points, price_type)
    return round(sum(prices) / len(prices), 4) if prices else None


def _highest(points: list[PricePoint], price_type: str) -> float | None:
    prices = _today_prices(points, price_type)
    return max(prices) if prices else None


@dataclass(frozen=True, kw_only=True)
class AnwbEnergieSensorDescription(SensorEntityDescription):
    """Describes an ANWB Energie price sensor."""

    commodity: str
    price_type: str
    value_fn: Callable[[list[PricePoint], str], float | None]
    with_price_attributes: bool = False


def _price_sensor(
    key: str, commodity: str, price_type: str
) -> AnwbEnergieSensorDescription:
    return AnwbEnergieSensorDescription(
        key=key,
        translation_key=key,
        commodity=commodity,
        price_type=price_type,
        value_fn=_current,
        with_price_attributes=True,
        native_unit_of_measurement=(
            ELECTRICITY_UNIT if commodity == COMMODITY_ELECTRICITY else GAS_UNIT
        ),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    )


def _statistic_sensor(
    key: str, value_fn: Callable[[list[PricePoint], str], float | None]
) -> AnwbEnergieSensorDescription:
    return AnwbEnergieSensorDescription(
        key=key,
        translation_key=key,
        commodity=COMMODITY_ELECTRICITY,
        price_type=PRICE_ALL_IN,
        value_fn=value_fn,
        native_unit_of_measurement=ELECTRICITY_UNIT,
        suggested_display_precision=2,
    )


SENSORS: tuple[AnwbEnergieSensorDescription, ...] = (
    _price_sensor("stroom_all_in", COMMODITY_ELECTRICITY, PRICE_ALL_IN),
    _price_sensor("stroom_marktprijs", COMMODITY_ELECTRICITY, PRICE_MARKET),
    _price_sensor("gas_all_in", COMMODITY_GAS, PRICE_ALL_IN),
    _price_sensor("gas_marktprijs", COMMODITY_GAS, PRICE_MARKET),
    _statistic_sensor("stroom_laagste_vandaag", _lowest),
    _statistic_sensor("stroom_gemiddeld_vandaag", _average),
    _statistic_sensor("stroom_hoogste_vandaag", _highest),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnwbEnergieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ANWB Energie sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        AnwbEnergieSensor(coordinator, description) for description in SENSORS
    )


class AnwbEnergieSensor(CoordinatorEntity[AnwbEnergieCoordinator], SensorEntity):
    """Sensor with the ANWB Energie price for the current hour or day."""

    entity_description: AnwbEnergieSensorDescription
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    # The hourly price lists change every hour; keep them out of the database.
    _unrecorded_attributes = frozenset({"raw_today", "raw_tomorrow"})

    def __init__(
        self,
        coordinator: AnwbEnergieCoordinator,
        description: AnwbEnergieSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.entity_id = f"sensor.{DOMAIN}_{description.key}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="ANWB Energie",
            manufacturer="ANWB",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Update the state at the start of every hour."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._async_hour_changed, minute=0, second=0
            )
        )

    @callback
    def _async_hour_changed(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def _points(self) -> list[PricePoint]:
        return self.coordinator.data.get(self.entity_description.commodity, [])

    @property
    def native_value(self) -> float | None:
        """Return the price."""
        return self.entity_description.value_fn(
            self._points, self.entity_description.price_type
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the hourly prices for today and tomorrow."""
        if not self.entity_description.with_price_attributes:
            return None

        price_type = self.entity_description.price_type
        now = datetime.now(TIMEZONE)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        # Add in UTC: on the autumn DST day, local +1h would skip the repeated hour.
        next_hour = price_at(self._points, now.astimezone(UTC) + timedelta(hours=1))

        return {
            "price_type": price_type,
            "next_hour": next_hour.price(price_type) if next_hour else None,
            "today_min": _lowest(self._points, price_type),
            "today_avg": _average(self._points, price_type),
            "today_max": _highest(self._points, price_type),
            "tomorrow_valid": is_day_complete(self._points, tomorrow),
            "raw_today": self._raw(today),
            "raw_tomorrow": self._raw(tomorrow),
        }

    def _raw(self, day: date) -> list[dict[str, Any]]:
        price_type = self.entity_description.price_type
        return [
            {
                "start": point.start.isoformat(),
                "end": point.end.isoformat(),
                "value": price,
            }
            for point in prices_for_day(self._points, day)
            if (price := point.price(price_type)) is not None
        ]
