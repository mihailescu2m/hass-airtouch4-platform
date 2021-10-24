from __future__ import annotations

import asyncio

from .protocol import *

import logging
_LOGGER = logging.getLogger(__name__)

class Airtouch4():
    def __init__(self, host, port=9004):
        self._host = host
        self._port = port
        self.connected = False
        self.groups_info = {}
        self.groups = []
        self.acs_info = {}
        self.acs = []
        self._reader = None
        self._writer = None
        self._queue = asyncio.Queue()
        self._groups_ready = asyncio.Event()
        self._acs_ready = asyncio.Event()
        asyncio.create_task(self._init())

    async def _init(self) -> None:
        await self._connect()
        asyncio.create_task(self._publish())
        
    async def _connect(self) -> None:
        _LOGGER.debug("(Re)connecting...")
        while not self.connected:
            try:
                self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
            except:
                self.connected = False
                await asyncio.sleep(5)
                continue
            self.connected = True
            _LOGGER.debug("(Re)connected!")
        asyncio.create_task(self._subscribe())
        await self.request_group_info()
        await self.request_group_status()
        await self.request_ac_info()
        await self.request_ac_status()
    
    async def ready(self) -> bool:
        await self._groups_ready.wait()
        await self._acs_ready.wait()
        return True

    async def _read_msg(self) -> Message:
        header = await self._reader.readexactly(6)
        if bytes(header[:2]) != HEADER_BYTES:
            _LOGGER.error("Message received with invalid header!")
            return None
        extended = False
        if header[2:4] == bytes(reversed(EXTENDED_ADDRESS_BYTES)):
            extended = True
        elif header[2:4] != bytes(reversed(ADDRESS_BYTES)):
            _LOGGER.info("Message received with invalid address!")

        size_bytes = await self._reader.readexactly(2)
        size = int.from_bytes(size_bytes, ENDIANNESS)
        data = await self._reader.readexactly(size)
        crc_bytes = await self._reader.readexactly(2)
        crc = int.from_bytes(crc_bytes, ENDIANNESS)
        if crc != crc16(header[2:] + size_bytes + data):
            _LOGGER.error("Message received with invalid crc!")
            return None

        msg_id = header[4]
        msg_type = header[5]
        return Message(data, msg_type, msg_id, extended)

    async def _subscribe(self) -> None:
        _LOGGER.debug("Message listener (re)started...")
        while self.connected:
            try:
                while msg := await self._read_msg():
                    if msg.type == MSGTYPE_GRP_STAT:
                        groups = msg.decode_groups_status()
                        for group in groups:
                            existing = next((g for g in self.groups if g.group_number == group), None)
                            if not existing:
                                self.groups.append(AirtouchGroupStatus(**groups[group].__dict__))
                            else:
                                existing.update(groups[group].__dict__)
                        if len(self.groups): self._groups_ready.set()
                    elif msg.type == MSGTYPE_AC_STAT:
                        acs = msg.decode_acs_status()
                        for ac in acs:
                            existing = next((u for u in self.acs if u.ac_unit_number == ac), None)
                            if not existing:
                                self.acs.append(AirtouchACStatus(**acs[ac].__dict__))
                            else:
                                existing.update(acs[ac].__dict__)
                        if len(self.acs): self._acs_ready.set()
                    elif msg.type == MSGTYPE_EXTENDED:
                        if msg.data[:2] == MSG_EXTENDED_GROUP_DATA:
                            self.groups_info.update(msg.decode_groups_info())
                        elif msg.data[:2] == MSG_EXTENDED_AC_DATA:
                            self.acs_info.update(msg.decode_acs_info())
            except ConnectionError:
                _LOGGER.error("Connection error in listener, disconnect!")
                self.connected = False
                self._reader = None
                self._writer = None
        asyncio.create_task(self._connect())
        _LOGGER.debug("Message listener finished after scheduling a reconnect...")

    async def _write_msg(self, msg: Message) -> None:
        size_bytes, data = msg.encode()
        self._writer.writelines([size_bytes, data])
        await self._writer.drain()

    async def _publish(self) -> None:
        while True:
            while msg := await self._queue.get():
                try:
                    await self._write_msg(msg)
                except:
                    _LOGGER.error("Connection error in publisher, disconnect!")
                    self.connected = False
                    self._reader = None
                    self._writer = None
                    await asyncio.sleep(5)
                    self._queue.put_nowait(msg)
                self._queue.task_done()

    async def request_group_status(self) -> None:
        self._queue.put_nowait(Message.GROUP_STATUS_REQUEST())
    
    async def request_group_info(self) -> None:
        self._queue.put_nowait(Message.GROUP_EXTENDED_REQUEST())

    async def request_group_open_perc(self, group: int, percentage: int) -> None:
        msg = Message.GROUP_CONTROL_REQUEST(group_number=group, target_type=GROUP_TARGET_TYPES.DAMPER, target=int(percentage))
        self._queue.put_nowait(msg)

    async def request_group_target_temp(self, group: int, temp: int) -> None:
        msg = Message.GROUP_CONTROL_REQUEST(group_number=group, target_type=GROUP_TARGET_TYPES.TEMPERATURE, target=int(temp))
        self._queue.put_nowait(msg)

    async def request_group_control_type(self, group: int, control_type: int) -> None:
        msg = Message.GROUP_CONTROL_REQUEST(group_number=group, control_type=control_type)
        self._queue.put_nowait(msg)

    async def request_group_power(self, group, power: int) -> None:
        msg = Message.GROUP_CONTROL_REQUEST(group_number=group, power=power)
        self._queue.put_nowait(msg)

    async def request_ac_status(self) -> None:
        self._queue.put_nowait(Message.AC_STATUS_REQUEST())

    async def request_ac_info(self) -> None:
        self._queue.put_nowait(Message.AC_EXTENDED_REQUEST())
    
    async def request_ac_hvac_mode(self, ac: int, mode: int) -> None:
        msg = Message.AC_CONTROL_REQUEST(unit_number=ac, mode=mode)
        self._queue.put_nowait(msg)

    async def request_ac_fan_mode(self, ac: int, fan_mode: int) -> None:
        msg = Message.AC_CONTROL_REQUEST(unit_number=ac, fan_speed=fan_mode)
        self._queue.put_nowait(msg)

    async def request_ac_target_temp(self, ac: int, temp: int) -> None:
        msg = Message.AC_CONTROL_REQUEST(unit_number=ac, target=temp)
        self._queue.put_nowait(msg)

    async def request_ac_power(self, ac: int, power: int) -> None:
        msg = Message.AC_CONTROL_REQUEST(unit_number=ac, power=power)
        self._queue.put_nowait(msg)
