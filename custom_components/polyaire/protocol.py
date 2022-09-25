from __future__ import annotations
from typing import Any, Callable

import os
from types import SimpleNamespace

import logging
_LOGGER = logging.getLogger(__name__)

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc = crc ^ byte
        for _ in range(8):
            odd = crc & 0x0001
            crc = crc >> 1
            if odd: crc = crc ^ 0xA001
    return crc

ENDIANNESS = "big"

HEADER_BYTES = bytes([0x55, 0x55])
ADDRESS_BYTES = bytes([0x80, 0xb0])
EXTENDED_ADDRESS_BYTES = bytes([0x90, 0xb0])

MSGTYPE_GRP_CTRL = 0x2a
MSGTYPE_GRP_STAT = 0x2b
MSGTYPE_AC_CTRL = 0x2c
MSGTYPE_AC_STAT = 0x2d
MSGTYPE_EXTENDED = 0x1f

MSG_NO_DATA = bytes([])
MSG_EXTENDED_ERROR_DATA = bytes([0xff, 0x10])
MSG_EXTENDED_AC_DATA = bytes([0xff, 0x11])
MSG_EXTENDED_GROUP_DATA = bytes([0xff, 0x12])

AC_TARGET_KEEP = 63

class PRESETS(SimpleNamespace):
    DAMPER = "Damper"
    ITC = "ITC"
    TURBO = "Turbo"

class GROUP_POWER_STATES(SimpleNamespace):
    KEEP = 0
    NEXT = 1
    OFF = 2
    ON = 3
    TURBO = 5

class GROUP_CONTROL_TYPES(SimpleNamespace):
    KEEP = 0
    NEXT = 1
    DAMPER = 2
    TEMPERATURE = 3

class GROUP_TARGET_TYPES(SimpleNamespace):
    KEEP = 0
    DECREMENT = 2
    INCREMENT = 3
    DAMPER = 4
    TEMPERATURE = 5

class AC_POWER_STATES(SimpleNamespace):
    KEEP = 0
    NEXT = 1
    OFF = 2
    ON = 3

class AC_MODES(SimpleNamespace):
    AUTO = 0
    HEAT = 1
    DRY = 2
    FAN = 3
    COOL = 4
    KEEP = 5

class AC_FAN_SPEEDS(SimpleNamespace):
    AUTO = 0
    QUIET = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    POWERFUL = 5
    TURBO = 6
    KEEP = 7

class AC_TARGET_TYPES(SimpleNamespace):
    KEEP = 0
    SET_VALUE = 1
    DECREMENT = 2
    INCREMENT = 3

class Updateable(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._callbacks = set()

    def __hash__(self):
        return hash(self.__dict__)

    def __iter__(self):
        for key in self.__dict__:
            if not key.startswith("_"):
                yield key, getattr(self, key)

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when a device changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    def update(self, status: dict) -> bool:
        updated = False
        for key, value in status.items():
            if hasattr(self, key) and type(value) is not set and getattr(self, key) != value:
                setattr(self, key, value)
                updated = True
        if updated:
            for callback in self._callbacks:
                id = self.group_number if hasattr(self, "group_number") else self.ac_unit_number
                _LOGGER.debug("Updated " + self.__class__.__name__ + " " + str(id) + " status, calling: " + str(callback))
                callback()

class AirTouchGroupStatus(Updateable):
    group_power_state: int
    group_number: int
    group_control_type: int
    group_open_perc: int
    group_battery_low: int
    group_has_turbo: int
    group_target: int
    group_has_sensor: int
    group_temp: float
    group_has_spill: int

class AirTouchACStatus(Updateable):
    ac_power_state: int
    ac_unit_number: int
    ac_mode: int
    ac_fan_speed: int
    ac_spill: int
    ac_timer: int
    ac_target: int
    ac_temp: float
    ac_error_code: int

class Message:
    def __init__(self, data: bytes, type: int, id: int = None, extended: bool = False):
        self.data = data
        self.type = type
        self.id = id or os.urandom(1)
        self.extended = extended

    def isValid(self) -> bool:
        return (self.id is not None
                and self.type is not None
                and self.data is not None)

    def encode(self) -> tuple[bytes, bytes]:
        size_bytes = len(self.data).to_bytes(2, ENDIANNESS)
        address = EXTENDED_ADDRESS_BYTES if self.extended else ADDRESS_BYTES
        payload = address + self.id + self.type.to_bytes(1, ENDIANNESS) + size_bytes + self.data
        crc = crc16(payload)
        crc_bytes = crc.to_bytes(2, ENDIANNESS)
        message = HEADER_BYTES + payload + crc_bytes
        return len(message).to_bytes(4, ENDIANNESS), message

    def decode_groups_status(self) -> dict[int, AirTouchGroupStatus]:
        if not self.isValid():
            return None
        groups = dict()
        chunk = 6
        for group in [self.data[i:i+chunk] for i in range(0, len(self.data), chunk)]:
            group_number = group[0] & 0b00111111
            groups[group_number] = AirTouchGroupStatus(
                group_power_state = (group[0] & 0b11000000) >> 6,
                group_number = group_number,
                group_control_type = (group[1] & 0b10000000) >> 7,
                group_open_perc = group[1] & 0b01111111,
                group_battery_low = (group[2] & 0b10000000) >> 7,
                group_has_turbo = (group[2] & 0b01000000) >> 6,
                group_target = (group[2] & 0b00111111) * 1.0,
                group_has_sensor = (group[3] & 0b10000000) >> 7,
                group_temp = (((group[4] << 3) + ((group[5] & 0b11100000) >> 5)) - 500) / 10,
                group_has_spill = (group[5] & 0b00010000) >> 4
            )
        return groups
    
    def decode_groups_info(self) -> dict[int, str]:
        if not self.isValid():
            return None
        groups_info = dict()
        data = self.data[2:]
        chunk = 9
        for group in [data[i:i+chunk] for i in range(0, len(data), chunk)]:
            group_number = group[0]
            group_name = group[1:].decode("utf-8").rstrip("\x00")
            groups_info[group_number] = group_name
        return groups_info

    def decode_acs_status(self) -> dict[int, AirTouchACStatus]:
        if not self.isValid():
            return None
        acs = dict()
        chunk = 8
        for ac in [self.data[i:i+chunk] for i in range(0, len(self.data), chunk)]:
            ac_unit_number = ac[0] & 0b00111111
            acs[ac_unit_number] = AirTouchACStatus(
                ac_power_state = (ac[0] & 0b11000000) >> 6,
                ac_unit_number = ac_unit_number,
                ac_mode = (ac[1] & 0b11110000) >> 4,
                ac_fan_speed = ac[1] & 0b00001111,
                ac_spill = (ac[2] & 0b10000000) >> 7,
                ac_timer = (ac[2] & 0b01000000) >> 6,
                ac_target = (ac[2] & 0b00111111) * 1.0,
                ac_temp = (((ac[4] << 3) + ((ac[5] & 0b11100000) >> 5)) - 500) / 10,
                ac_error_code = (ac[6] << 8) + (ac[7])
            )
        return acs

    def decode_acs_info(self) -> dict[int, Any]:
        if not self.isValid():
            return None
        acs_info = dict()
        data = self.data[2:]
        chunk = int(len(data)/int(len(data)/24))
        for ac in [data[i:i+chunk] for i in range(0, len(data), chunk)]:
            ac_unit_number = ac[0]
            acs_info[ac_unit_number] = {
                "ac_unit_name": ac[2:18].decode("utf-8").rstrip("\x00"),
                "ac_group_start": ac[18],
                "ac_group_count": ac[19],
                "ac_min_temp": ac[22],
                "ac_max_temp": ac[23],
                "ac_modes": {
                    4: bool(ac[20] & 0b00010000),   # COOL
                    3: bool(ac[20] & 0b00001000),   # FAN
                    2: bool(ac[20] & 0b00000100),   # DRY
                    1: bool(ac[20] & 0b00000010),   # HEAT
                    0: bool(ac[20] & 0b00000001),   # AUTO
                },
                "fan_modes": {
                    6: bool(ac[21] & 0b01000000),   # TURBO
                    5: bool(ac[21] & 0b00100000),   # POWERFUL
                    4: bool(ac[21] & 0b00010000),   # HIGH
                    3: bool(ac[21] & 0b00001000),   # MEDIUM
                    2: bool(ac[21] & 0b00000100),   # LOW
                    1: bool(ac[21] & 0b00000010),   # QUIET
                    0: bool(ac[21] & 0b00000001),   # AUTO
                }
            }
        return acs_info

    @classmethod
    def GROUP_CONTROL_REQUEST(cls, group_number: int, power: int = None, control_type: int = GROUP_CONTROL_TYPES.KEEP, target_type: int = GROUP_TARGET_TYPES.KEEP, target: int = 0) -> Message:
        if power is None:
            power_state = GROUP_POWER_STATES.KEEP
        elif power == 0:
            power_state = GROUP_POWER_STATES.OFF
        elif power == 3:
            power_state = GROUP_POWER_STATES.TURBO
        else:
            power_state = GROUP_POWER_STATES.ON

        byte1 = group_number.to_bytes(1, ENDIANNESS)
        byte2 = (power_state | (control_type << 3) | (target_type << 5)).to_bytes(1, ENDIANNESS)
        byte3 = target.to_bytes(1, ENDIANNESS)
        byte4 = (0).to_bytes(1, ENDIANNESS)
        data  = byte1 + byte2 + byte3 + byte4
        return Message(data, MSGTYPE_GRP_CTRL)

    @classmethod
    def GROUP_STATUS_REQUEST(cls) -> Message:
        return Message(MSG_NO_DATA, MSGTYPE_GRP_STAT)

    @classmethod
    def GROUP_EXTENDED_REQUEST(cls) -> Message:
        return Message(MSG_EXTENDED_GROUP_DATA, MSGTYPE_EXTENDED, extended=True)

    @classmethod
    def AC_CONTROL_REQUEST(cls, unit_number: int, power: int = None, mode: int = AC_MODES.KEEP, fan_speed: int = AC_FAN_SPEEDS.KEEP, target: int = AC_TARGET_KEEP) -> Message:
        if mode != AC_MODES.KEEP or power:
            power_state = AC_POWER_STATES.ON
        elif power == 0:
            power_state = AC_POWER_STATES.OFF
        else:
            power_state = AC_POWER_STATES.KEEP

        byte1 = (unit_number | (power_state << 6)).to_bytes(1, ENDIANNESS)
        byte2 = (fan_speed | (mode << 4)).to_bytes(1, ENDIANNESS)
        byte3 = (target | (AC_TARGET_TYPES.KEEP << 6)).to_bytes(1, ENDIANNESS)
        byte4 = (0).to_bytes(1, ENDIANNESS)
        data  = byte1 + byte2 + byte3 + byte4
        return Message(data, MSGTYPE_AC_CTRL)

    @classmethod
    def AC_STATUS_REQUEST(cls) -> Message:
        return Message(MSG_NO_DATA, MSGTYPE_AC_STAT)

    @classmethod
    def AC_EXTENDED_REQUEST(cls) -> Message:
        return Message(MSG_EXTENDED_AC_DATA, MSGTYPE_EXTENDED, extended=True)
