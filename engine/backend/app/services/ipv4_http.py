"""HTTPS requests that always go out over IPv4.

Binance's API-key whitelist only understands IPv4 addresses. A server with both stacks may reach Binance over
IPv6, which Binance then sees as an address that is not on the whitelist and rejects with -2015 — while every
IPv4 check on the same machine looks perfect. So every call that depends on the whitelist uses this opener.
"""

from __future__ import annotations

import http.client
import socket
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = socket._GLOBAL_DEFAULT_TIMEOUT  # type: ignore[attr-defined]


def connect_ipv4(address: tuple[str, int], timeout: Any = DEFAULT_TIMEOUT,
                 source_address: tuple[str, int] | None = None) -> socket.socket:
    """`socket.create_connection`, restricted to the host's IPv4 addresses."""
    host, port = address
    candidates = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    failure: OSError | None = None
    for family, kind, protocol, _canonical, sockaddr in candidates:
        sock = socket.socket(family, kind, protocol)
        try:
            if timeout is not DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as error:
            sock.close()
            failure = error
    raise failure or OSError(f"{host} has no IPv4 address")


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    _create_connection = staticmethod(connect_ipv4)


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):  # type: ignore[override]
        return self.do_open(IPv4HTTPSConnection, request, context=self._context)


_opener = urllib.request.build_opener(_IPv4HTTPSHandler())


def urlopen_ipv4(request: urllib.request.Request, timeout: float):
    """Like `urlopen`, but never over IPv6. Raises the same errors, so callers need no changes."""
    return _opener.open(request, timeout=timeout)
