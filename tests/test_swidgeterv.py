"""Checks for SwidgetERV, built from the summary and state of a real FV-15ESC1 (firmware 1.6.125).

Needs only aiohttp. Run with: python -m pytest tests  (or: python tests/test_swidgeterv.py)
"""
import asyncio
import os
import sys

# Import the client package on its own: the integration package needs Home Assistant
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "swidget"))
from swidgetclient import swidgeterv  # noqa: E402
from swidgetclient.discovery import _get_device_class  # noqa: E402

SUMMARY = {"model": "FAN_PICO_S3", "mac": "020000000001", "version": "1.6.125",
           "insert": {"type": "control", "components": []},
           "host": {"id": "testErvDeviceId00001", "type": "pesna_IB150", "error": 0, "components": [
               {"id": "0", "functions": ["power", "toggle", "dutyCycle", "exhaust", "supply", "mode", "boost",
                                         "error", "raw", "outdoors", "indoors", "balancing"],
                "maxCFM": 150, "code": "8040"}]}}
STATE = {"insert": {"components": {}, "errors": {"self_diag": 0}},
         "host": {"components": {"0": {
             "toggle": {"state": "on"}, "power": {"current": 58.3, "avg": 57, "avgOn": 55.1},
             "dutyCycle": {"minutes": 0}, "exhaust": {"cfm": 91, "allowed": [0, 150]},
             "supply": {"cfm": 101, "default": 0, "allowed": [0, 150]}, "mode": "heatExchange",
             "status": "normal", "speed": "high", "boost": {"mode": "off"}, "error": {},
             "indoors": {"temperature": 21, "humidity": 50}, "outdoors": {"temperature": 11, "humidity": 254},
             "filter": {"needsReplacement": False, "needsCleaning": True},
             "balancing": {"offset": 0, "state": "off"}}}},
         "connection": {"rssi": -67, "ip": "192.0.2.130", "type": "wifi", "mac": "02:00:00:00:00:01"}}


async def _check():
    assert _get_device_class("pesna_IB150") is swidgeterv.SwidgetERV
    erv = swidgeterv.SwidgetERV("192.0.2.1", "", False)
    try:
        await erv.process_summary(SUMMARY)
        await erv.process_state(STATE)
        sent = []

        async def send_command(assembly, component, function, command):
            sent.append((function, command))
            # The device echoes each command back as a state update
            await erv.process_state({"host": {"components": {"0": {function: command}}}})

        erv.send_command = send_command
        swidgeterv.BOOST_OFF_SETTLE_SECONDS = 0

        assert erv.is_erv and erv.is_on and erv.mode == "heatExchange" and erv.speed == "high"
        assert erv.airflow_range == [0, 150]
        values = erv.realtime_values
        assert values["power"] == 58.3 and values["supply_cfm"] == 101 and values["status"] == "normal"
        assert values["indoors_temperature"] == 21 and values["outdoors_humidity"] is None  # 254 = no reading
        assert values["filter_clean"] is True and values["error"] is False

        # Defrost: supply 0 and a placeholder outdoor reading. Keep the last real one until the supply runs again.
        defrost = {"supply": {"cfm": 0}, "outdoors": {"temperature": 53}, "status": "defrost"}
        await erv.process_state({"host": {"components": {"0": defrost}}})
        assert erv.realtime_values["outdoors_temperature"] == 11 and erv.realtime_values["status"] == "defrost"
        await erv.process_state({"host": {"components": {"0": {"supply": {"cfm": 85}, "outdoors": {"temperature": 8}}}}})
        assert erv.realtime_values["outdoors_temperature"] == 8

        await erv.set_speed("boost")
        assert sent == [("boost", {"mode": "on"})] and erv.speed == "boost"
        # Leaving boost: boost off first, then the speed, or the ERV ends up on low
        sent.clear()
        await erv.set_speed("high")
        assert sent == [("boost", {"mode": "off"}), ("speed", "high")] and erv.speed == "high"
        sent.clear()
        await erv.set_speed("low")
        assert sent == [("speed", "low")]
    finally:
        await erv.close()


def test_swidgeterv():
    asyncio.run(_check())


if __name__ == "__main__":
    test_swidgeterv()
    print("OK")
