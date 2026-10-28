"""Set up the integration in Home Assistant with mocked API responses."""

from datetime import timedelta
import json
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.anwb_energie_tarieven.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"
API = "https://api.anwb.nl/energy/energy-services/v3/tarieven"


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    for commodity, fixture in (
        ("electricity", "electricity_dst.json"),
        ("gas", "gas_dst.json"),
    ):
        aioclient_mock.get(
            f"{API}/{commodity}",
            json=json.loads((FIXTURES / fixture).read_text()),
        )
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The sensors show the price of the current hour and today's statistics."""
    freezer.move_to("2026-10-25T18:30:00+01:00")
    entry = await _setup(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.anwb_energie_stroom_all_in")
    assert float(state.state) == 0.29
    assert state.attributes["today_min"] == 0.12
    assert state.attributes["today_max"] == 0.29
    assert state.attributes["tomorrow_valid"] is False
    assert len(state.attributes["raw_today"]) == 25
    assert state.attributes["raw_tomorrow"] == []

    assert float(hass.states.get("sensor.anwb_energie_stroom_marktprijs").state) == 0.16
    assert hass.states.get("sensor.anwb_energie_stroom_laagste_vandaag").state == "0.12"
    assert hass.states.get("sensor.anwb_energie_stroom_hoogste_vandaag").state == "0.29"
    # The next gas day (from 06:00) was not published in the fixture.
    assert hass.states.get("sensor.anwb_energie_gas_all_in").state == "unknown"

    # Every request asks for hourly data.
    for _method, url, _data, _headers in aioclient_mock.mock_calls:
        assert url.query["interval"] == "HOUR"


async def test_state_follows_the_clock(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The state changes at the whole hour without a new API call."""
    freezer.move_to("2026-10-25T05:59:59+01:00")
    await _setup(hass, aioclient_mock)
    assert float(hass.states.get("sensor.anwb_energie_gas_all_in").state) == 1.91
    calls = aioclient_mock.call_count

    freezer.move_to("2026-10-25T06:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.anwb_energie_gas_all_in").state == "unknown"
    assert aioclient_mock.call_count == calls


async def test_api_error_retries_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failing API leaves the entry in setup-retry."""
    aioclient_mock.get(f"{API}/electricity", status=500)
    aioclient_mock.get(f"{API}/gas", status=500)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_api_error_keeps_last_prices(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed update keeps the last prices and retries after 5 minutes."""
    freezer.move_to("2026-10-25T18:30:00+01:00")
    entry = await _setup(hass, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/electricity", exc=TimeoutError)
    aioclient_mock.get(f"{API}/gas", exc=TimeoutError)
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2
    assert entry.runtime_data.update_interval == timedelta(minutes=5)
    # Still available, with the 19:00 price from the earlier response.
    assert float(hass.states.get("sensor.anwb_energie_stroom_all_in").state) == 0.26

    # Recovers at the next attempt, 5 minutes later instead of an hour.
    aioclient_mock.clear_requests()
    payload = json.loads((FIXTURES / "electricity_dst.json").read_text())
    for hour in payload["data"]:
        if hour["date"] == "2026-10-25T19:00:00+01:00":
            hour["values"]["allInPrijs"] = 99
    aioclient_mock.get(f"{API}/electricity", json=payload)
    aioclient_mock.get(
        f"{API}/gas", json=json.loads((FIXTURES / "gas_dst.json").read_text())
    )
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2
    assert entry.runtime_data.update_interval == timedelta(hours=1)
    assert float(hass.states.get("sensor.anwb_energie_stroom_all_in").state) == 0.99


async def test_gas_error_keeps_new_electricity_prices(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When only gas fails, the newly fetched electricity prices are used."""
    freezer.move_to("2026-10-25T18:30:00+01:00")
    await _setup(hass, aioclient_mock)

    aioclient_mock.clear_requests()
    payload = json.loads((FIXTURES / "electricity_dst.json").read_text())
    for hour in payload["data"]:
        if hour["date"] == "2026-10-25T19:00:00+01:00":
            hour["values"]["allInPrijs"] = 99
    aioclient_mock.get(f"{API}/electricity", json=payload)
    aioclient_mock.get(f"{API}/gas", exc=TimeoutError)
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.anwb_energie_stroom_all_in").state) == 0.99
    assert hass.states.get("sensor.anwb_energie_gas_all_in").state != "unavailable"


async def test_outdated_prices_become_unavailable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the last prices no longer cover the current hour, the update fails."""
    freezer.move_to("2026-10-25T18:30:00+01:00")
    await _setup(hass, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/electricity", exc=TimeoutError)
    aioclient_mock.get(f"{API}/gas", exc=TimeoutError)
    # Tomorrow's prices were never published in the fixture.
    freezer.move_to("2026-10-26T01:30:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.anwb_energie_stroom_all_in")
    assert state.state == "unavailable"


async def test_next_hour_on_dst_day(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """next_hour does not skip the repeated 02:00 hour when the clock goes back."""
    payload = json.loads((FIXTURES / "electricity_dst.json").read_text())
    for hour in payload["data"]:
        if hour["date"] == "2026-10-25T02:00:00+01:00":
            hour["values"]["allInPrijs"] = 99
    aioclient_mock.get(f"{API}/electricity", json=payload)
    aioclient_mock.get(
        f"{API}/gas", json=json.loads((FIXTURES / "gas_dst.json").read_text())
    )
    freezer.move_to("2026-10-25T02:30:00+02:00")
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.anwb_energie_stroom_all_in")
    assert float(state.state) == 0.13
    assert state.attributes["next_hour"] == 0.99
