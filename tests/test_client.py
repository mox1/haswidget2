"""Checks for the client's HTTP error handling, SSDP parsing and setup cleanup.

Needs only aiohttp and ssdp. Run with: python -m pytest tests  (or: python tests/test_client.py)
"""
import asyncio
import os
import sys

# Import the client package on its own: the integration package needs Home Assistant
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "swidget"))
from swidgetclient import discovery  # noqa: E402
from swidgetclient.device import SwidgetDevice  # noqa: E402
from swidgetclient.exceptions import (  # noqa: E402
    SwidgetAuthError,
    SwidgetException,
    SwidgetUnsupportedDevice,
)


class FakeResponse:
    def __init__(self, status=200, body=None, error=None):
        self.status, self.body, self.error = status, body, error

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self.body


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)

    def request(self, method, url, **kwargs):
        assert kwargs["timeout"] is not None, "every HTTP call needs a timeout"
        return self.responses.pop(0)

    async def close(self):
        pass


async def _check_request_errors():
    device = SwidgetDevice("192.0.2.1", "key", False, use_websockets=False)
    await device._session.close()
    device._session = FakeSession(
        FakeResponse(401), FakeResponse(500), FakeResponse(error=TimeoutError()), FakeResponse(body={"name": "erv"})
    )
    for expected in (SwidgetAuthError, SwidgetException, SwidgetException):
        try:
            await device._request("GET", "/api/v1/state")
        except SwidgetException as err:
            assert type(err) is expected, (type(err), expected)
        else:
            raise AssertionError(f"expected {expected.__name__}")
    assert await device._request("GET", "/api/v1/name") == {"name": "erv"}


def _check_ssdp_parsing():
    protocol = discovery.SwidgetProtocol()
    reply = (
        "HTTP/1.1 200 OK\r\nST: urn:swidget:pico:1\r\nUSN: uuid:swidget-020000000001\r\n"
        'Location: https://192.0.2.130/\r\nSERVER: Swidget/1.0 pesna_IB150+control/"erv"\r\n\r\n'
    )
    protocol.datagram_received(reply.encode(), ("192.0.2.130", 1900))
    # None of these may raise: an exception here would reach the event loop's error log
    protocol.datagram_received(b"\xff\xfe not text", ("192.0.2.9", 1900))
    protocol.datagram_received(b"HTTP/1.1 200 OK\r\nST: urn:swidget:pico:1\r\n\r\n", ("192.0.2.8", 1900))
    protocol.datagram_received(b"HTTP/1.1 200 OK\r\nST: upnp:rootdevice\r\nUSN: x\r\n\r\n", ("192.0.2.7", 1900))
    assert list(protocol.devices) == ["020000000001"]
    found = protocol.devices["020000000001"]
    assert found.host == "192.0.2.130" and found.friendly_name == "erv"


async def _check_discover_single_cleanup():
    closed = []

    class Probe(SwidgetDevice):
        def __init__(self, *args, **kwargs):
            pass

        async def get_summary(self):
            self.device_type = self.probe_type

        async def close(self):
            closed.append("probe")

    class Broken(Probe):
        async def update(self):
            raise SwidgetException("device went away")

        async def close(self):
            closed.append("device")

    original = discovery.SwidgetDevice, discovery._get_device_class
    discovery.SwidgetDevice = Probe
    try:
        Probe.probe_type = "no_such_type"
        try:
            await discovery.discover_single("192.0.2.1", "", False)
        except SwidgetUnsupportedDevice:
            pass
        else:
            raise AssertionError("an unknown host type must raise SwidgetUnsupportedDevice")

        Probe.probe_type = "pesna_IB150"
        closed.clear()
        discovery._get_device_class = lambda device_type: Broken
        try:
            await discovery.discover_single("192.0.2.1", "", False)
        except SwidgetException:
            pass
        else:
            raise AssertionError("a failed update must raise")
        assert closed == ["probe", "device"], closed
    finally:
        discovery.SwidgetDevice, discovery._get_device_class = original


def test_client():
    asyncio.run(_check_request_errors())
    _check_ssdp_parsing()
    asyncio.run(_check_discover_single_cleanup())


if __name__ == "__main__":
    test_client()
    print("OK")
