from homeassistant.components.fan import FanEntity
from homeassistant.components.fan import (
    SUPPORT_SET_SPEED,
    SUPPORT_PRESET_MODE,
)

from .const import DOMAIN
from .protocol import GROUP_CONTROL_TYPES, PRESETS

import logging
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the AirTouch 4 fan entities."""
    _LOGGER.debug("Setting up AirTouch fan entities...")
    airtouch = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for group in airtouch.groups:
        group_entity = AirTouchGroupDamper(airtouch, group)
        new_devices.append(group_entity)
    
    if new_devices:
        async_add_devices(new_devices)

class AirTouchGroupDamper(FanEntity):
    def __init__(self, airtouch, group):
        self._airtouch = airtouch
        self._group = group
        self._id = group.group_number
        self._name = airtouch.groups_info[group.group_number]
        _LOGGER.debug("Damper " + str(self._id) + ": created")
    
    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("Damper " + str(self._id) + ": registering callbacks")
        self._group.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("Damper " + str(self._id) + ": removing callbacks")
        self._group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "Damper " + self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_damper_" + str(self._id)

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return bool(self._group.group_power_state)

    @property
    def percentage(self):
        """Return the current speed percentage."""
        return self._group.group_open_perc

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return 20

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_PRESET_MODE | SUPPORT_SET_SPEED # (self._group.group_control_type == 0 and SUPPORT_SET_SPEED)

    @property
    def preset_mode(self):
        """Return preset mode."""
        if self._group.group_has_sensor and self._group.group_control_type == 1:
            return PRESETS.ITC
        return PRESETS.DAMPER

    @property
    def preset_modes(self):
        """Return preset modes."""
        presets = [PRESETS.DAMPER]
        if self._group.group_has_sensor:
            presets.append(PRESETS.ITC)
        return presets

    async def async_set_percentage(self, percentage):
        """Set the speed percentage of the fan."""
        if percentage == self.percentage or self.preset_mode != PRESETS.DAMPER:
            return
        await self._airtouch.request_group_open_perc(self._id, percentage) and self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set the preset mode of the fan."""
        if preset_mode == self.preset_mode:
            return
        control_type = GROUP_CONTROL_TYPES.DAMPER if preset_mode == PRESETS.DAMPER else GROUP_CONTROL_TYPES.TEMPERATURE
        await self._airtouch.request_group_control_type(self._id, control_type) and self.async_write_ha_state()

    async def async_turn_on(self, speed = None, percentage = None, preset_mode = None, **kwargs):
        """Turn on the fan."""
        await self._airtouch.request_group_power(self._id, 1)
        if percentage is not None:
            await self.async_set_percentage(percentage)
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        self.async_write_ha_state()
    
    async def async_turn_off(self, **kwargs):
        """Turn the fan off."""
        await self._airtouch.request_group_power(self._id, 0) and self.async_write_ha_state()
