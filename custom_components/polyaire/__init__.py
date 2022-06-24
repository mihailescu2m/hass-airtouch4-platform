from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import CONF_HOST

import asyncio

from .const import DOMAIN
from .airtouch4 import AirTouch4

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["climate", "fan"]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Airtouch 4 component."""
    # Ensure our name space for storing objects is a known type. A dict is
    # common/preferred as it allows a separate instance of your class for each
    # instance that has been created in the UI.
    _LOGGER.debug("async_setup: set default domain " + DOMAIN)
    hass.data.setdefault(DOMAIN, {})

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Airtouch4 from a config entry."""
    # Store an instance of the "connecting" class that does the work of speaking
    # with your actual devices.
    _LOGGER.debug("async_setup_entry: create airtouch hub for host " + entry.data[CONF_HOST])
    airtouch = AirTouch4(entry.data[CONF_HOST])
    try:
        _LOGGER.debug("async_setup_entry: waiting for airtouch connection to be ready...")
        await asyncio.wait_for(airtouch.ready(), 20)
    except asyncio.TimeoutError:
        _LOGGER.debug("async_setup_entry: timeout error waiting for airtouch, disconnecting...")
        await airtouch.disconnect()
        return False

    hass.data[DOMAIN][entry.entry_id] = airtouch

    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    for component in PLATFORMS:
        _LOGGER.debug("async_setup_entry: calling async_create_task for " + component)
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    _LOGGER.debug("async_unload_entry: unloading all components")
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    entry, component)
                for component in PLATFORMS
            ]
        )
    )

    if unload_ok:
        _LOGGER.debug("async_unload_entry: unload successful, now waiting for airtouch to disconnect...")
        airtouch = hass.data[DOMAIN].pop(entry.entry_id)
        await airtouch.disconnect()
    else:
        _LOGGER.debug("async_unload_entry: unload was not successful")

    _LOGGER.debug("async_unload_entry: exiting")
    return unload_ok
