from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_FOCUS,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_DRY,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_FAN,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_PRESET_MODE,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .protocol import GROUP_CONTROL_TYPES, PRESETS

import logging
_LOGGER = logging.getLogger(__name__)

POWER_ON = 1
POWER_OFF = 0

MAP_AC_MODE = {
    0: HVAC_MODE_AUTO,      # AUTO
    1: HVAC_MODE_HEAT,      # HEAT
    2: HVAC_MODE_DRY,       # DRY
    3: HVAC_MODE_FAN_ONLY,  # FAN
    4: HVAC_MODE_COOL,      # COOL
    8: HVAC_MODE_AUTO,      # AUTO-HEAT
    9: HVAC_MODE_AUTO       # AUTO-COOL
}

MAP_AC_FAN_MODE = {
    0: FAN_AUTO,            # AUTO
    1: FAN_DIFFUSE,         # QUIET
    2: FAN_LOW,             # LOW
    3: FAN_MEDIUM,          # MEDIUM
    4: FAN_HIGH,            # HIGH
    5: FAN_FOCUS,           # POWERFUL
    6: "turbo"              # TURBO
}

def MAP_VALUE_SEARCH(MAP: dict[int, Any], value: Any) -> int:
    return next((k for k, v in MAP.items() if v == value), None)

async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the AirTouch 4 climate entities."""
    _LOGGER.debug("Setting up AirTouch climate entities...")
    airtouch = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for ac in airtouch.acs:
        ac_entity = AirTouchACThermostat(airtouch, ac)
        new_devices.append(ac_entity)
    for group in airtouch.groups:
        if group.group_has_sensor:
            group_entity = AirTouchGroupThermostat(airtouch, group)
            new_devices.append(group_entity)
    
    if new_devices:
        async_add_devices(new_devices)

class AirTouchGroupThermostat(ClimateEntity):
    def __init__(self, airtouch, group):
        self._airtouch = airtouch
        self._group = group
        self._ac = airtouch.get_group_ac(group.group_number)
        self._ac_min_temp = airtouch.acs_info[self._ac.ac_unit_number]["ac_min_temp"]
        self._ac_max_temp = airtouch.acs_info[self._ac.ac_unit_number]["ac_max_temp"]
        self._id = group.group_number
        self._name = airtouch.groups_info[group.group_number]
        _LOGGER.debug("ITC Thermostat " + str(self._id) + ": created")
        _LOGGER.debug("ITC Thermostat " + str(self._id) + " belongs to: AC " + str(self._ac.ac_unit_number))
    
    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("ITC Thermostat " + str(self._id) + ": registering callbacks")
        self._group.register_callback(self.async_write_ha_state)
        # self._ac.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("ITC Thermostat " + str(self._id) + ": removing callbacks")
        # self._ac.remove_callback(self.async_write_ha_state)
        self._group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "ITC " + self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_itc_" + str(self._id)

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS
    
    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._group.group_temp
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._group.group_target

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1.0

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._group.group_control_type == 1:
            return self._ac_min_temp
        return self._group.group_target

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._group.group_control_type == 1:
            return self._ac_max_temp
        return self._group.group_target

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported."""
        if self.hvac_mode == HVAC_MODE_OFF:
            return CURRENT_HVAC_OFF
        elif self._ac.ac_power_state == POWER_OFF:
            return CURRENT_HVAC_IDLE
        elif self._ac.ac_mode == MAP_VALUE_SEARCH(MAP_AC_MODE, HVAC_MODE_HEAT):
            return CURRENT_HVAC_HEAT
        elif self._ac.ac_mode == MAP_VALUE_SEARCH(MAP_AC_MODE, HVAC_MODE_COOL):
            return CURRENT_HVAC_COOL
        elif self._ac.ac_mode == MAP_VALUE_SEARCH(MAP_AC_MODE, HVAC_MODE_DRY):
            return CURRENT_HVAC_DRY
        elif self._ac.ac_mode == MAP_VALUE_SEARCH(MAP_AC_MODE, HVAC_MODE_FAN_ONLY):
            return CURRENT_HVAC_FAN
        return None

    @property
    def hvac_mode(self):
        """Return current operation mode."""
        if self._group.group_power_state == POWER_ON:
            return HVAC_MODE_AUTO
        return HVAC_MODE_OFF

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return [HVAC_MODE_AUTO, HVAC_MODE_OFF]

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_PRESET_MODE | (self._group.group_control_type == 1 and SUPPORT_TARGET_TEMPERATURE)

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

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == self.hvac_mode and hvac_mode != HVAC_MODE_OFF:
            return
        elif hvac_mode == HVAC_MODE_OFF and self.hvac_mode != HVAC_MODE_OFF:
            await self._airtouch.request_group_power(self._id, POWER_OFF)
        else:
            await self._airtouch.request_group_power(self._id, POWER_ON)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None or temp == self.target_temperature:
            return
        await self._airtouch.request_group_target_temp(self._id, temp) and self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set the preset mode of the fan."""
        if preset_mode == self.preset_mode:
            return
        control_type = GROUP_CONTROL_TYPES.DAMPER if preset_mode == PRESETS.DAMPER else GROUP_CONTROL_TYPES.TEMPERATURE
        await self._airtouch.request_group_control_type(self._id, control_type) and self.async_write_ha_state()

class AirTouchACThermostat(ClimateEntity):
    def __init__(self, airtouch, ac):
        self._airtouch = airtouch
        self._ac = ac
        self._id = ac.ac_unit_number
        self._info = airtouch.acs_info[ac.ac_unit_number]
        self._groups = airtouch.get_ac_groups(ac.ac_unit_number)
        _LOGGER.debug("AC " + str(self._id) + ": created")
    
    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The airtouch device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        _LOGGER.debug("AC " + str(self._id) + ": registering callbacks")
        self._ac.register_callback(self.async_write_ha_state)
        for group in self._groups:
           group.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        _LOGGER.debug("AC " + str(self._id) + ": removing callbacks")
        self._ac.remove_callback(self.async_write_ha_state)
        for group in self._groups:
            group.remove_callback(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name for this device."""
        return "AC " + self._info["ac_unit_name"]

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return "polyaire_ac_" + str(self._id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Polyaire",
            model="AirTouch 4",
            name=self.name
        )

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS
    
    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._ac.ac_temp
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._ac.ac_target

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1.0

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        itc_control = sum([group.group_control_type for group in self._groups if group.group_power_state == POWER_ON])
        total_active = len([group for group in self._groups if group.group_power_state == POWER_ON])
        if itc_control == total_active:
            # all groups are controlled by ITC, AC temperature control is disabled
            if self.hvac_mode == HVAC_MODE_HEAT or self._ac.ac_mode == 8:
                # heat: max(groups)
                temp = self._info["ac_min_temp"]
                for group in self._groups:
                    if group.group_target > temp and group.group_power_state == POWER_ON:
                        temp = group.group_target
                return temp
            elif self.hvac_mode == HVAC_MODE_COOL or self._ac.ac_mode == 9:
                # cool: min(groups)
                temp = self._info["ac_max_temp"]
                for group in self._groups:
                    if group.group_target < temp and group.group_power_state == POWER_ON:
                        temp = group.group_target
                return temp
            else:
                return None
        elif itc_control > 0 and (self.hvac_mode == HVAC_MODE_HEAT or self._ac.ac_mode == 8):
            # heat: max(groups)
            temp = self._info["ac_min_temp"]
            for group in self._groups:
                if group.group_control_type and group.group_target > temp and group.group_power_state == POWER_ON:
                    temp = group.group_target
            return temp
        return self._info["ac_min_temp"]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        itc_control = sum([group.group_control_type for group in self._groups if group.group_power_state == POWER_ON])
        total_active = len([group for group in self._groups if group.group_power_state == POWER_ON])
        if itc_control == total_active:
            # all groups are controlled by ITC, AC temperature control is disabled
            if self.hvac_mode == HVAC_MODE_HEAT or self._ac.ac_mode == 8:
                # heat: max(groups)
                temp = self._info["ac_min_temp"]
                for group in self._groups:
                    if group.group_target > temp and group.group_power_state == POWER_ON:
                        temp = group.group_target
                return temp
            elif self.hvac_mode == HVAC_MODE_COOL or self._ac.ac_mode == 9:
                # cool: min(groups)
                temp = self._info["ac_max_temp"]
                for group in self._groups:
                    if group.group_target < temp and group.group_power_state == POWER_ON:
                        temp = group.group_target
                return temp
            else:
                return None
        elif itc_control > 0 and (self.hvac_mode == HVAC_MODE_COOL or self._ac.ac_mode == 9):
            # cool: min(groups)
            temp = self._info["ac_max_temp"]
            for group in self._groups:
                if group.group_control_type and group.group_target < temp and group.group_power_state == POWER_ON:
                    temp = group.group_target
            return temp
        return self._info["ac_max_temp"]

    @property
    def hvac_mode(self):
        """Return current operation mode."""
        if self._ac.ac_power_state == POWER_OFF:
            return HVAC_MODE_OFF
        return MAP_AC_MODE[self._ac.ac_mode]

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        modes = [HVAC_MODE_OFF]
        for mode, enabled in self._info["ac_modes"].items():
            if enabled: modes.extend([MAP_AC_MODE[mode]])
        return modes

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return MAP_AC_FAN_MODE[self._ac.ac_fan_speed]

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        modes = []
        for mode, enabled in self._info["fan_modes"].items():
            if enabled: modes.extend([MAP_AC_FAN_MODE[mode]])
        return modes

    @property
    def supported_features(self):
        """Return the list of supported features."""
        itc_control = sum([group.group_control_type for group in self._groups if group.group_power_state == POWER_ON])
        total_active = len([group for group in self._groups if group.group_power_state == POWER_ON])
        return (itc_control < total_active and SUPPORT_TARGET_TEMPERATURE) | (len(self.fan_modes) > 0 and SUPPORT_FAN_MODE)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == self.hvac_mode and hvac_mode != HVAC_MODE_OFF:
            return
        elif hvac_mode == HVAC_MODE_OFF and self.hvac_mode != HVAC_MODE_OFF:
            await self.async_turn_off()
        elif hvac_mode == HVAC_MODE_OFF and self.hvac_mode == HVAC_MODE_OFF:
            await self.async_turn_on()
        else:
            mode = MAP_VALUE_SEARCH(MAP_AC_MODE, hvac_mode)
            mode is not None and await self._airtouch.request_ac_hvac_mode(self._id, mode)
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        if fan_mode == self.fan_mode:
            return
        mode = MAP_VALUE_SEARCH(MAP_AC_FAN_MODE, fan_mode)
        mode is not None and await self._airtouch.request_ac_fan_mode(self._id, mode) and self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None or temp == self.target_temperature:
            return
        await self._airtouch.request_ac_target_temp(self._id, int(temp)) and self.async_write_ha_state()

    async def async_turn_on(self):
        """Turn on."""
        await self._airtouch.request_ac_power(self._id, POWER_ON) and self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off."""
        await self._airtouch.request_ac_power(self._id, POWER_OFF) and self.async_write_ha_state()
