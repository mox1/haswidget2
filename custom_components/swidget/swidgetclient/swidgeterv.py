import asyncio

from .device import SwidgetDevice

# The ERV reports 254 for a temperature or humidity it cannot read (no airflow over the sensor)
NO_READING = 254
# Ending boost drops the ERV to low about 0.5 s later, which undoes a speed sent sooner
BOOST_OFF_SETTLE_SECONDS = 1.5


class SwidgetERV(SwidgetDevice):
    """A Panasonic Intelli-Balance ERV (host type pesna_*) behind a WP100PBA module."""

    @property
    def _fan(self) -> dict:
        return self.assemblies["host"].components["0"].functions

    async def _command(self, function: str, command):
        await self.send_command(assembly="host", component="0", function=function, command=command)

    async def get_state(self):
        """Also re-read the settings, at setup and after every reconnect."""
        await super().get_state()
        await self.get_device_config()

    async def process_state(self, state):
        """Keep the last outdoor reading while the supply is 0: no outdoor air reaches the sensor then."""
        outdoors = self._fan.get("outdoors")
        await super().process_state(state)
        # During defrost the ERV sends {"temperature": 53}, a placeholder, and no humidity
        if (self._fan.get("supply") or {}).get("cfm") == 0:
            self._fan["outdoors"] = outdoors

    @property
    def is_on(self) -> bool:
        return self._fan["toggle"]["state"] == "on"

    async def turn_on(self):
        await self._command("toggle", {"state": "on"})

    async def turn_off(self):
        await self._command("toggle", {"state": "off"})

    @property
    def speed(self) -> str:
        """Return "low", "high" or "boost"."""
        if self._fan["boost"].get("mode", "off") != "off":
            return "boost"
        return self._fan["speed"]

    async def set_speed(self, speed: str):
        if speed == "boost":
            await self._command("boost", {"mode": "on"})
            return
        if self.speed == "boost":
            await self._command("boost", {"mode": "off"})
            # shortcut: fixed pause, measured on firmware 1.6.125; wait for the state echo if it ever fails
            await asyncio.sleep(BOOST_OFF_SETTLE_SECONDS)
        await self._command("speed", speed)

    @property
    def mode(self) -> str:
        """Return "heatExchange", "supply", "exhaust" or "recirculation"."""
        return self._fan["mode"]

    async def set_mode(self, mode: str):
        await self._command("mode", mode)

    async def reset_filter(self):
        """Reset the filter run time, as the Filter Reset button on the ERV does."""
        await self._command("filter", {"clean": True})

    @property
    def airflow_range(self) -> list:
        """Return the [min, max] airflow in CFM that the ERV allows."""
        return self._fan["supply"]["allowed"]

    @property
    def settings(self) -> dict:
        """Return the ERV settings from device_config (airflow per speed, runtime, humidity control)."""
        return self.device_config["host"]["components"]["0"]

    async def set_setting(self, key: str, value):
        await self.update_device_config({"host": {"components": {"0": {key: value}}}})
        # Re-read: the ERV silently rejects values out of range, and runtime also clears autoRuntime
        await self.get_device_config()

    @property
    def realtime_values(self) -> dict:
        fan = self._fan
        filter_state = fan.get("filter") or {}
        values = {
            "power": fan["power"]["current"],
            "supply_cfm": fan["supply"]["cfm"],
            "exhaust_cfm": fan["exhaust"]["cfm"],
            "status": fan.get("status"),
            "filter_replace": filter_state.get("needsReplacement"),
            "filter_clean": filter_state.get("needsCleaning"),
            "error": bool(fan.get("error")),
            "rssi": self.rssi,
        }
        # Only models whose summary lists indoors/outdoors have those sensors
        for place in ("indoors", "outdoors"):
            if place in fan:
                for reading in ("temperature", "humidity"):
                    value = (fan[place] or {}).get(reading)
                    values[f"{place}_{reading}"] = None if value == NO_READING else value
        return values
