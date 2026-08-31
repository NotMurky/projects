"""Minimal, dependency-free Minecraft RCON client (Source RCON protocol).

Synchronous, single-connection, with a lock so a background poll loop and an
on-demand command (e.g. an in-game /hours reply) can share one instance safely.
"""
from __future__ import annotations

import socket
import struct
import threading

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RconError(Exception):
    pass


class RconAuthError(RconError):
    pass


class MCRcon:
    def __init__(self, host: str, port: int, password: str, timeout: float = 8.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._reqid = 0
        self._lock = threading.RLock()

    # -- low level ---------------------------------------------------------
    def _connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        if not self._authenticate():
            self.close()
            raise RconAuthError("RCON authentication failed (bad password?)")

    def _next_id(self) -> int:
        self._reqid = (self._reqid + 1) & 0x7FFFFFFF
        return self._reqid

    def _send(self, ptype: int, body: str) -> int:
        assert self._sock is not None
        reqid = self._next_id()
        payload = struct.pack("<ii", reqid, ptype) + body.encode("utf-8") + b"\x00\x00"
        self._sock.sendall(struct.pack("<i", len(payload)) + payload)
        return reqid

    def _recv(self) -> tuple[int, int, str]:
        assert self._sock is not None
        raw_len = self._read_exact(4)
        (length,) = struct.unpack("<i", raw_len)
        data = self._read_exact(length)
        reqid, ptype = struct.unpack("<ii", data[:8])
        body = data[8:-2].decode("utf-8", "replace")
        return reqid, ptype, body

    def _read_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise RconError("connection closed by server")
            buf += chunk
        return buf

    def _authenticate(self) -> bool:
        sent_id = self._send(SERVERDATA_AUTH, self.password)
        # Servers may send an empty RESPONSE_VALUE first; loop until AUTH_RESPONSE.
        while True:
            reqid, ptype, _ = self._recv()
            if ptype == SERVERDATA_AUTH_RESPONSE:
                return reqid == sent_id  # -1 => failure
            # ignore the priming RESPONSE_VALUE packet

    # -- public ------------------------------------------------------------
    def command(self, cmd: str) -> str:
        """Run a command, reconnecting once if the socket is stale."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._sock is None:
                        self._connect()
                    sent_id = self._send(SERVERDATA_EXECCOMMAND, cmd)
                    reqid, ptype, body = self._recv()
                    return body
                except (OSError, RconError) as exc:
                    self.close()
                    if attempt == 2 or isinstance(exc, RconAuthError):
                        raise
            return ""  # unreachable

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
