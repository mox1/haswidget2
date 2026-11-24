# SwidgetERV

A Home Assistant integration for Swidget devices on the local network, with support for Panasonic Intelli-Balance ERVs on the WP100PBA module. It is a fork of [michaelkkehoe/haswidget2](https://github.com/michaelkkehoe/haswidget2). It needs Home Assistant 2026.7 or newer.

## Installation

To install the integration with HACS, do these steps:

1. In HACS, open the three-dot menu and select Custom repositories.
2. Enter `https://github.com/mox1/haswidget2` and select the type Integration.
3. Find SwidgetERV in HACS and select Download.
4. Restart Home Assistant.

If you copied the integration by hand before, delete the old `custom_components/swidget` folder first. Your devices and entities stay, because the integration domain is still `swidget`.

## Setup

To add a device by its IP address, do these steps:

1. In Home Assistant, open the Devices & services page.
2. Select Add integration, then select SwidgetERV. If the integration is already installed, open it and select Add device.
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

## Examples

[examples/automations/erv_co2_control.yaml](examples/automations/erv_co2_control.yaml) sets the airflow of an ERV from the CO2 level in the house. Below 550 ppm the automation turns the ERV off. From 550 to 1000 ppm the airflow ramps up. The supply runs 20 CFM above the exhaust, to keep a slight positive pressure in the house. At 1000 ppm and above, both run at 150 CFM. If the automation turned the ERV off, it turns the ERV on again at 575 ppm. It records this in a Toggle helper. If you turn the ERV off, it stays off. If you turn the ERV on by hand below 550 ppm, the automation turns it off again within 5 minutes. The file explains how to add it and which values to change.

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
- While the supply airflow is 0, no outdoor air reaches the outdoor sensor. The integration then keeps the last outdoor temperature and humidity, and Home Assistant shows how old they are. During defrost, the ERV reports 53 °C and no humidity in place of a reading.
- Below about -5 °C (23 °F) outdoors, the ERV goes into frost prevention, and Status shows defrost. Status stays defrost until it is warmer outside. With frost prevention set to Exhaust, the ERV repeats a cycle of about 28 minutes. For about 20 minutes the airflow is normal. For about 8 minutes the supply is 0 and the exhaust is about 140 CFM.
- While it is this cold, the installation manual says that the ERV limits the airflow to 120 CFM. It also limits the difference between supply and exhaust to 20 CFM.
- At the start and end of each defrost period, the ERV reports off for 15 to 45 seconds. The Ventilation fan shows off for that time. Automations that react to the fan turning off also see these short offs.
- The ERV stores any airflow value, also values above its maximum. The integration limits the airflow to the range that the ERV reports, for example 0 to 150 CFM.
