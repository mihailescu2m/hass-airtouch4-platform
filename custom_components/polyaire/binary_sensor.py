import string
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .const import DOMAIN

import logging
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the AirTouch 4 battery entities."""
    _LOGGER.debug("Setting up AirTouch battery entities...")
    airtouch = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for group in airtouch.groups:
        battery_sensor = AirTouchGroupBattery(airtouch, group)
        new_devices.append(battery_sensor)
        turbo_sensor = AirTouchGroupTurbo(airtouch, group)
        new_devices.append(turbo_sensor)
        spill_sensor = AirTouchGroupBattery(airtouch, group)
        new_devices.append(spill_sensor)
    
    if new_devices:
        async_add_devices(new_devices)

class AirTouchGroupBattery(BinarySensorEntity):
    def __init__(self, airtouch, group):
        self._airtouch = airtouch
        self._group = group
        self._id = group.group_number
        self._name = airtouch.groups_info[group.group_number]
        _LOGGER.debug("ITC Battery " + str(self._id) + ": created")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("ITC Battery " + str(self._id) + ": registering callbacks")
        self._group.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("ITC Battery " + str(self._id) + ": removing callbacks")
        self._group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "ITC LowBattery " + self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_itc_battery_" + str(self._id)

    @property
    def is_on(self) -> bool:
        """Returns if the binary sensor is currently on or off."""
        """Battery: On means low, Off means normal."""
        return self._group.group_battery_low

    @property
    def device_class(self) -> string:
        """Return the type of binary sensor."""
        return BinarySensorDeviceClass.BATTERY

class AirTouchGroupTurbo(BinarySensorEntity):
    def __init__(self, airtouch, group):
        self._airtouch = airtouch
        self._group = group
        self._id = group.group_number
        self._name = airtouch.groups_info[group.group_number]
        _LOGGER.debug("Zone Turbo Sensor " + str(self._id) + ": created")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("Zone Turbo Sensor " + str(self._id) + ": registering callbacks")
        self._group.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("Zone Turbo Sensor " + str(self._id) + ": removing callbacks")
        self._group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "Zone Turbo " + self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_zone_turbo_" + str(self._id)

    @property
    def is_on(self) -> bool:
        """Returns if the binary sensor is currently on or off."""
        """Battery: On means low, Off means normal."""
        return self._group.group_has_turbo and self._group.group_power_state == 3

    @property
    def device_class(self) -> string:
        """Return the type of binary sensor."""
        return BinarySensorDeviceClass.RUNNING

class AirTouchGroupSpill(BinarySensorEntity):
    def __init__(self, airtouch, group):
        self._airtouch = airtouch
        self._group = group
        self._id = group.group_number
        self._name = airtouch.groups_info[group.group_number]
        _LOGGER.debug("Zone Spill Sensor " + str(self._id) + ": created")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("Zone Spill Sensor " + str(self._id) + ": registering callbacks")
        self._group.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("Zone Spill Sensor " + str(self._id) + ": removing callbacks")
        self._group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "Zone Spill " + self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_zone_spill_" + str(self._id)

    @property
    def is_on(self) -> bool:
        """Returns if the binary sensor is currently on or off."""
        """Battery: On means low, Off means normal."""
        return self._group.group_has_spill

    @property
    def device_class(self) -> string:
        """Return the type of binary sensor."""
        return BinarySensorDeviceClass.OPENING
