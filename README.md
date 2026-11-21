# haswidget2

A Home Assistant integration for Swidget devices on the local network. It needs Home Assistant 2026.7 or newer.

## Setup

To add a device by its IP address, do these steps:

1. In Home Assistant, open the Devices & services page.
2. Select Add integration, then select Swidget. If the integration is already installed, open it and select Add device.
3. Enter the IP address of the device.
4. Enter the access key. If authentication is turned off on the device, leave the access key empty.

To search the network instead, leave the IP address empty. Home Assistant also finds devices through SSDP and DHCP and shows them under Discovered.

Give each device a DHCP reservation, so that its address does not change. If the address changes, open the device entry and select Reconfigure.

If Home Assistant cannot reach a device at startup, it retries in the background. When the device is back, for example after a power outage, it connects again. If the device rejects the access key, setup stops and the log says so. To enter a new key, use Reconfigure.

## Logging

When a device goes offline, the integration writes one INFO line. When the device comes back, it writes one more INFO line. If a device rejects the access key, the integration writes one ERROR line. A command that fails, for example while a device is offline, gives one ERROR line without a traceback.

To see all messages, for example to report a problem, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.swidget: debug
```

## Panasonic ERV (WP100PBA module)

The integration supports Panasonic Intelli-Balance energy recovery ventilators (ERVs) with a Swidget WP100PBA Wi-Fi control module. The module reports a host type that starts with `pesna_`, for example `pesna_IB150` on an FV-15ESC1. Testing used an FV-15ESC1 with module firmware 1.6.125.

The integration creates these entities for an ERV. Each entity name starts with the device name.

| Entity | Type | What it does |
|---|---|---|
| Ventilation | Fan | Turns the ERV on or off. The preset sets the speed: Low, High or Boost. |
| Mode | Select | Ventilate (heat exchange), Supply, Exhaust or Recirculate. |
| Power, Supply airflow, Exhaust airflow | Sensor | Current power (W) and airflow (CFM). |
| Indoor and outdoor temperature and humidity | Sensor | Readings from the ERV sensors. |
| Status | Sensor | normal, defrost, boost, humidity, auto, int, limit, balancing or unknown. |
| Filter needs replacement, Filter needs cleaning, Error | Binary sensor | On when the ERV reports the problem. |
| Reset filter | Button | Resets the filter run time, as the Filter Reset button on the ERV does. |
| Low, High and Boost supply and exhaust airflow | Number | The airflow (CFM) for each speed. |
| Intermittent runtime | Number | Minutes per hour (1 to 60) for intermittent operation. |
| Intermittent runtime auto | Switch | The ASHRAE automatic runtime ("Aut" on the ERV panel). |
| Humidity control, Humidity control setpoint | Switch, Number | Boosts the airflow while the indoor humidity is above the setpoint (30 to 80 %). |
| Mesh balancing | Switch | The `balancing` configuration value. It is most likely the flag for fan balancing over the Swidget Bluetooth mesh. It is not the bLS setting on the ERV panel. |
| Intermittent mode, Outside humidity sensing | Switch | ERV configuration values. Their effect is not confirmed. |
| Supply limit at low temperature, Supply limit at high humidity, and their thresholds | Switch, Number | ERV configuration values. Their effect is not confirmed. |

Home Assistant shows all Number and Switch entities of the ERV, and Reset filter, in the Configuration section of the device page.

### ERV behavior

- If the duct installation is dC4 or dC5, the ERV does not allow recirculation. The ERV then ignores the Recirculate mode.
- When boost ends, the ERV drops to Low. To go from Boost to High, the integration ends boost, waits 1.5 seconds, and then sets High.
- The ERV accepts a boost timer, but on firmware 1.6.125 boost continues after the timer ends. The integration does not offer the timer. To boost for a fixed time, use an automation that sets Boost and then, after a delay, sets Low or High.
- If you set Intermittent runtime, the ERV turns Intermittent runtime auto off. This is the same as on the ERV panel.
- The module cannot read or set the auto balancing mode (bLS). To change it, use the ERV panel.
- If the ERV cannot read a temperature or humidity, it reports 254. If there is no airflow, the ERV cannot read them. The integration shows these readings as unknown.
- The ERV stores any airflow value, also values above its maximum. The integration limits the airflow to the range that the ERV reports, for example 0 to 150 CFM.
