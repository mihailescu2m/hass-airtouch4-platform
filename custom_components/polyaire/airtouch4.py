from __future__ import annotations

import asyncio
import socket

from .protocol import *

import logging
_LOGGER = logging.getLogger(__name__)

class AirTouch4():
    def __init__(self, host, port=9004):
        self._host = host
        self._port = port
        self.want_connection = True
        self.connected = False
        self.groups = []
        self.groups_info = {}
        self._groups_ready = asyncio.Event()
        self.acs = []
        self.acs_info = {}
        self._acs_ready = asyncio.Event()
        self._reader = None
        self._receiver = None
        self._writer = None
        self._sender = None
        self._queue = asyncio.Queue()
        _LOGGER.debug("created new airtouch hub, waiting to connect to the host...")
        asyncio.create_task(self._connect())

    def get_group_ac(self, group_number: int) -> int:
        ac_unit_number = 0
        ac_group_start = 0
        for unit_number, info in self.acs_info.items():
            if info["ac_group_start"] <= group_number and info["ac_group_start"] > ac_group_start:
                ac_unit_number = unit_number
                ac_group_start = info["ac_group_start"]
        return self.acs[ac_unit_number]

    def get_ac_groups(self, unit_number: int) -> list[int]:
        ac_group_start = self.acs_info[unit_number]["ac_group_start"]
        ac_group_end = len(self.groups)
        for unit_number, info in self.acs_info.items():
            if info["ac_group_start"] > ac_group_start and info["ac_group_start"] < ac_group_end:
                ac_group_end = info["ac_group_start"]
        return [group for group in self.groups if group.group_number in range(ac_group_start, ac_group_end)]


    async def _connect(self) -> None:
        while self.want_connection and not self.connected:
            _LOGGER.info("(Re)connecting...")
            try:
                _LOGGER.debug("open socket connection to the airtouch...")
                task = asyncio.open_connection(self._host, self._port)
                self._reader, self._writer = await asyncio.wait_for(task, 10)
            except socket.gaierror:
                _LOGGER.error("Cannot find AirTouch host, giving up...")
                return
            except asyncio.TimeoutError:
                _LOGGER.error("Cannot connect to AirTouch host, giving up...")
                return
            except Exception:
                # try again on disconnect
                _LOGGER.warning("Error connecting to AirTouch host, trying again in 5s...")
                self.connected = False
                await asyncio.sleep(5)
                continue
            self.connected = True
            _LOGGER.info("(Re)connected!")
        if not self.want_connection:
            return
        # start receiver task
        if not self._receiver or self._receiver.done():
            self._receiver = asyncio.create_task(self._receive())
        # start sender task
        if not self._sender or self._sender.done():
            self._sender = asyncio.create_task(self._send())

    async def disconnect(self):
        _LOGGER.info("Disconnecting...")
        self.want_connection = False
        if self.connected:
            # close socket/writer with IncompleteReadError
            self._writer.close()
            await self._writer.wait_closed()
        if self._receiver and not self._receiver.done():
            self._receiver.cancel()
        if self._sender and not self._sender.done():
            self._sender.cancel()
    
    async def ready(self) -> None:
        # request info from AirTouch
        if not self._groups_ready.is_set():
            await self.request_group_info()
            await self.request_group_status()
        if not self._acs_ready.is_set():
            await self.request_ac_info()
            await self.request_ac_status()
        # wait for status response
        await self._groups_ready.wait()
        await self._acs_ready.wait()
        _LOGGER.info("Received all status information from AirTouch, ready to go!")

    async def _read_msg(self) -> Message:
        header = await self._reader.readexactly(6)
        if bytes(header[:2]) != HEADER_BYTES:
            _LOGGER.error("Message received with invalid header!")
            return None
        unknown = False
        extended = False
        # if header[2:4] == bytes(reversed(EXTENDED_ADDRESS_BYTES)):
        if header[3] == EXTENDED_ADDRESS_BYTES[0]:
            _LOGGER.debug("Message received with extended header!")
            extended = True
        # elif header[2:4] != bytes(reversed(ADDRESS_BYTES)):
        elif header[3] != ADDRESS_BYTES[0]:
            _LOGGER.warning("Message received with unknown header: " + str(header[2:4]))
            unknown = True
        else:
            _LOGGER.debug("Message received with expected header!")

        size_bytes = await self._reader.readexactly(2)
        size = int.from_bytes(size_bytes, ENDIANNESS)
        data = await self._reader.readexactly(size)
        crc_bytes = await self._reader.readexactly(2)
        crc = int.from_bytes(crc_bytes, ENDIANNESS)
        if crc != crc16(header[2:] + size_bytes + data):
            _LOGGER.error("Message received has invalid crc!")
            return None
        elif unknown:
            if (size_bytes):
                _LOGGER.warning("Unknown message:")
                _LOGGER.warning(data)
            return None

        msg_id = header[4]
        msg_type = header[5]
        return Message(data, msg_type, msg_id, extended)

    async def _receive(self) -> None:
        _LOGGER.info("Message receiver task (re)started...")
        while self.connected:
            try:
                while msg := await self._read_msg():
                    if msg.type == MSGTYPE_GRP_STAT:
                        _LOGGER.debug("Message received is group message!")
                        groups = msg.decode_groups_status()
                        for group in groups:
                            existing = next((g for g in self.groups if g.group_number == group), None)
                            if not existing:
                                self.groups.append(AirTouchGroupStatus(**groups[group].__dict__))
                            else:
                                existing.update(groups[group].__dict__)
                        if len(self.groups): self._groups_ready.set()
                    elif msg.type == MSGTYPE_AC_STAT:
                        _LOGGER.debug("Message received is AC message!")
                        acs = msg.decode_acs_status()
                        for ac in acs:
                            existing = next((u for u in self.acs if u.ac_unit_number == ac), None)
                            if not existing:
                                self.acs.append(AirTouchACStatus(**acs[ac].__dict__))
                            else:
                                existing.update(acs[ac].__dict__)
                        if len(self.acs): self._acs_ready.set()
                        ### workaround for group messages not being received ###
                        ### TODO: remove this after issues is fixed by Polyaire ###
                        await self.request_group_status()
                    elif msg.type == MSGTYPE_EXTENDED:
                        _LOGGER.debug("Message received is extended message!")
                        if msg.data[:2] == MSG_EXTENDED_GROUP_DATA:
                            self.groups_info.update(msg.decode_groups_info())
                            _LOGGER.debug(self.groups_info)
                        elif msg.data[:2] == MSG_EXTENDED_AC_DATA:
                            self.acs_info.update(msg.decode_acs_info())
                            _LOGGER.debug(self.acs_info)
                    else:
                        _LOGGER.debug("Message received with unknown type: " + hex(msg.type))
                        _LOGGER.debug(msg.data)
            except Exception: # asyncio.IncompleteReadError
                _LOGGER.error("Connection error in receiver!")
                self.connected = False
                self._reader = None
                self._writer = None
        _LOGGER.info("Message receiver lost connection, trying to reconnect...")
        asyncio.create_task(self._connect())

    async def _write_msg(self, msg: Message) -> None:
        size_bytes, data = msg.encode()
        self._writer.writelines([size_bytes, data])
        await self._writer.drain()

    async def _send(self) -> None:
        _LOGGER.info("Message sender task (re)started...")
        while (self.want_connection) and (msg := await self._queue.get()):
            try:
                await self._write_msg(msg)
            except Exception:
                _LOGGER.error("Error sending message! Deleting existing connection and retry sending in 5 seconds...")
                _LOGGER.debug("PS: somebody else should restart the connection, we'll just try retry sending in 5s...")
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

    async def request_group_control_type(self, group: int, control_type: int = GROUP_CONTROL_TYPES.KEEP, power: int = None) -> None:
        msg = Message.GROUP_CONTROL_REQUEST(group_number=group, control_type=control_type, power=power)
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
