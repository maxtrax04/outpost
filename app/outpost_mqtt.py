#!/usr/bin/env python3
"""
A small MQTT 3.1.1 client that only subscribes (docs/sensors-design.md), for the sensor and power
panels' mqtt: readings.

It connects to one broker, subscribes to exact topics at QoS 0 (no + or # wildcards, so the broker
sends only what is listed), and hands each message to a callback. Retained messages give a value
right away. It pings to keep the connection alive and, when the broker goes away, connects again
after a growing delay (up to 5 minutes). It never publishes.

The password is never logged, and the log names topics without their values.

Uses only the Python standard library (socket and ssl).
"""

import os
import socket
import ssl
import sys
import threading
import time
from typing import Callable, Iterable, List, Optional, Tuple

PROTOCOL_LEVEL = 4  # MQTT 3.1.1
KEEPALIVE_SECONDS = 60
CONNECT_TIMEOUT = 10
FIRST_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 300
# A connection that lasted this long starts the retry delay over
STEADY_SECONDS = 60
# Bigger messages are skipped (no reading is that big)
MAX_PACKET_BYTES = 256 * 1024
MAX_TOPICS = 100

CONNECT, CONNACK, PUBLISH, PUBACK, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT = 1, 2, 3, 4, 8, 9, 12, 13, 14

CONNACK_REASONS = {
    1: "the broker doesn't speak MQTT 3.1.1",
    2: "the broker refused the client ID",
    3: "the broker is unavailable",
    4: "the username or password was refused",
    5: "not authorized (check the username and password)",
}


def _say(message: str) -> None:
    print(f"[Outpost] {message}", file=sys.stderr, flush=True)


class ProtocolError(Exception):
    """The broker sent something this client can't follow, or refused it."""


def remaining_length(length: int) -> bytes:
    """MQTT's variable-length integer: 7 bits a byte, high bit set when more follow."""
    if not 0 <= length <= 268_435_455:
        raise ValueError("packet too long")
    out = bytearray()
    while True:
        byte, length = length % 128, length // 128
        out.append(byte | (0x80 if length else 0))
        if not length:
            return bytes(out)


def text(value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > 65535:
        raise ValueError("string too long")
    return len(data).to_bytes(2, "big") + data


def packet(kind: int, flags: int, body: bytes) -> bytes:
    return bytes([(kind << 4) | flags]) + remaining_length(len(body)) + body


def connect_packet(client_id: str, username: str = "", password: str = "",
                   keepalive: int = KEEPALIVE_SECONDS) -> bytes:
    flags = 0x02  # clean session: nothing is kept on the broker between connections
    payload = text(client_id)
    if username:
        flags |= 0x80
        payload += text(username)
        if password:
            flags |= 0x40
            payload += text(password)
    body = text("MQTT") + bytes([PROTOCOL_LEVEL, flags]) + keepalive.to_bytes(2, "big") + payload
    return packet(CONNECT, 0, body)


def subscribe_packet(packet_id: int, topics: Iterable[str]) -> bytes:
    body = packet_id.to_bytes(2, "big") + b"".join(text(topic) + b"\x00" for topic in topics)
    return packet(SUBSCRIBE, 0x02, body)


def parse_publish(flags: int, body: bytes) -> Tuple[str, bytes, int, Optional[int]]:
    """(topic, payload, qos, packet id) of a PUBLISH."""
    if len(body) < 2:
        raise ProtocolError("short PUBLISH")
    size = int.from_bytes(body[:2], "big")
    if len(body) < 2 + size:
        raise ProtocolError("short PUBLISH")
    try:
        topic = body[2:2 + size].decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("PUBLISH topic is not UTF-8")
    rest = body[2 + size:]
    qos = (flags >> 1) & 0x03
    packet_id = None
    if qos:
        if len(rest) < 2:
            raise ProtocolError("short PUBLISH")
        packet_id, rest = int.from_bytes(rest[:2], "big"), rest[2:]
    return topic, bytes(rest), qos, packet_id


class Reader:
    """Splits bytes from the broker into packets: feed() returns (type, flags, body) for each whole
    packet so far. Packets over MAX_PACKET_BYTES are skipped as they arrive, never kept."""

    def __init__(self, limit: int = MAX_PACKET_BYTES) -> None:
        self.limit = limit
        self.buffer = bytearray()
        self.skipping = 0
        self.skipped = 0

    def feed(self, data: bytes) -> List[Tuple[int, int, bytes]]:
        self.buffer += data
        packets = []
        while True:
            if self.skipping:
                dropped = min(self.skipping, len(self.buffer))
                del self.buffer[:dropped]
                self.skipping -= dropped
                if self.skipping:
                    return packets
            header = self._header()
            if header is None:
                return packets
            first, used, length = header
            if length > self.limit:
                del self.buffer[:used]
                self.skipping = length
                self.skipped += 1
                continue
            if len(self.buffer) < used + length:
                return packets
            body = bytes(self.buffer[used:used + length])
            del self.buffer[:used + length]
            packets.append((first >> 4, first & 0x0F, body))

    def _header(self) -> Optional[Tuple[int, int, int]]:
        """(first byte, header size, body length), or None until the whole header is here."""
        if len(self.buffer) < 2:
            return None
        length, multiplier = 0, 1
        for index in range(1, 5):
            if index >= len(self.buffer):
                return None
            byte = self.buffer[index]
            length += (byte & 0x7F) * multiplier
            multiplier *= 128
            if not byte & 0x80:
                return self.buffer[0], index + 1, length
        raise ProtocolError("bad packet length")


Message = Callable[[str, bytes], None]
Connector = Callable[[str, int, float], socket.socket]


def tcp_connect(host: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)


class Client:
    """Subscribes to `topics` on one broker and calls on_message(topic, payload) for each message,
    from its own thread (run). on_alive() is called whenever the broker is heard from, and
    on_state(connected) when the connection comes or goes."""

    def __init__(self, host: str, port: int, topics: Iterable[str], on_message: Message,
                 username: str = "", password: str = "", tls: bool = False,
                 keepalive: int = KEEPALIVE_SECONDS, connect: Connector = tcp_connect,
                 on_alive: Optional[Callable[[], None]] = None,
                 on_state: Optional[Callable[[bool], None]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 tls_context: Optional[ssl.SSLContext] = None) -> None:
        self.host = host
        self.port = port
        self.topics = list(dict.fromkeys(topics))[:MAX_TOPICS]
        self.on_message = on_message
        self.username = username
        self.password = password
        self.tls = tls
        self.keepalive = keepalive
        self.connect = connect
        self.on_alive = on_alive or (lambda: None)
        self.on_state = on_state or (lambda connected: None)
        self.clock = clock
        self.tls_context = tls_context
        self.client_id = "outpost-" + os.urandom(6).hex()
        self.connected = False
        self._problem: Optional[str] = None
        self._ever = False

    def _open(self) -> socket.socket:
        sock = self.connect(self.host, self.port, CONNECT_TIMEOUT)
        if self.tls:
            context = self.tls_context or ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.host)
        return sock

    def session(self, stop: threading.Event) -> None:
        """One connection: CONNECT, SUBSCRIBE, then messages until the broker goes or `stop` is set."""
        sock = self._open()
        try:
            sock.settimeout(1.0)
            reader = Reader()
            sock.sendall(connect_packet(self.client_id, self.username, self.password, self.keepalive))
            last_sent = last_heard = self.clock()
            waiting_ping = False
            subscribed = False
            while not stop.is_set():
                now = self.clock()
                if now - last_heard > self.keepalive * 1.5:
                    raise ProtocolError("the broker stopped answering")
                if subscribed and not waiting_ping and now - last_sent >= self.keepalive / 2:
                    sock.sendall(packet(PINGREQ, 0, b""))
                    last_sent, waiting_ping = now, True
                try:
                    data = sock.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    raise ProtocolError("the broker closed the connection")
                last_heard = self.clock()
                for kind, flags, body in reader.feed(data):
                    self.on_alive()
                    if kind == CONNACK:
                        code = body[1] if len(body) >= 2 else 255
                        if code:
                            raise ProtocolError(CONNACK_REASONS.get(code, f"the broker refused (code {code})"))
                        sock.sendall(subscribe_packet(1, self.topics))
                        last_sent = self.clock()
                    elif kind == SUBACK:
                        refused = [topic for topic, code in zip(self.topics, body[2:]) if code == 0x80]
                        for topic in refused:
                            _say(f"Sensors: the MQTT broker refused topic {topic}")
                        subscribed = True
                        self._set_connected(True)
                    elif kind == PUBLISH:
                        topic, payload, qos, packet_id = parse_publish(flags, body)
                        if qos == 1 and packet_id is not None:
                            sock.sendall(packet(PUBACK, 0, packet_id.to_bytes(2, "big")))
                            last_sent = self.clock()
                        if topic in self.topics and qos < 2:
                            self.on_message(topic, payload)
                    elif kind == PINGRESP:
                        waiting_ping = False
            try:
                sock.sendall(packet(DISCONNECT, 0, b""))
            except OSError:
                pass
        finally:
            self._set_connected(False)
            sock.close()

    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            if connected:
                if self._problem:
                    _say("Sensors: MQTT broker connected again")
                elif not self._ever:
                    _say(f"Sensors: MQTT broker connected, {len(self.topics)} "
                         f"topic{'' if len(self.topics) == 1 else 's'}")
                self._problem, self._ever = None, True
            self.on_state(connected)

    def _report(self, problem: str, retry: float) -> None:
        """Logs a problem once, until a connection works again."""
        if problem != self._problem:
            _say(f"Sensors: MQTT broker: {problem}; trying again in {int(retry)} s, then less often")
            self._problem = problem

    def run(self, stop: Optional[threading.Event] = None) -> None:
        """Connects, and connects again whenever the connection ends, until `stop` is set."""
        stop = stop or threading.Event()
        delay = FIRST_RETRY_SECONDS
        while not stop.is_set():
            started = self.clock()
            problem = None
            try:
                self.session(stop)
            except ssl.SSLError as error:
                problem = f"TLS failed ({error.reason or type(error).__name__})"
            except ProtocolError as error:
                problem = str(error)
            except (OSError, ValueError) as error:
                problem = f"can't connect ({type(error).__name__})"
            except Exception as error:  # keep going whatever goes wrong
                problem = f"failed ({type(error).__name__})"
            if stop.is_set():
                return
            if self.clock() - started >= STEADY_SECONDS:
                delay = FIRST_RETRY_SECONDS
            self._report(problem or "the connection ended", delay)
            stop.wait(delay)
            delay = min(MAX_RETRY_SECONDS, delay * 2)
