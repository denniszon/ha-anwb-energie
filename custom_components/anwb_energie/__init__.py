"""The ANWB Energie integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnwbEnergieClient
from .coordinator import AnwbEnergieConfigEntry, AnwbEnergieCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AnwbEnergieConfigEntry) -> bool:
    """Set up ANWB Energie from a config entry."""
    coordinator = AnwbEnergieCoordinator(
        hass, entry, AnwbEnergieClient(async_get_clientsession(hass))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AnwbEnergieConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
