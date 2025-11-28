<div align="center">

# 🐔 ha-run-chicken

Home Assistant integration for the Run‑Chicken Automatic Chicken Door

</div>

## Overview

`ha-run-chicken` is a custom Home Assistant component that connects to Run‑Chicken brand automatic chicken doors over Bluetooth. It has been tested with the T50 model (Bluetooth version) and should work with other Run‑Chicken models that expose the same Bluetooth service and characteristics.

This is a local push integration — it communicates directly with the door via Bluetooth and does not require cloud access or an internet connection.

## Features

- Open and close the door on demand
- Report current door state (open/closed)
- Local Bluetooth communication (no cloud required)

Planned/possible future additions:
- Battery level reporting
- Temperature and brightness sensors

## Requirements

- Home Assistant
- A host with working Bluetooth (BLE) near the coop
  - Example: Raspberry Pi 4/5, Home Assistant Yellow/Green, or a USB BLE adapter
- A compatible Run‑Chicken door (tested on T50 with Bluetooth)

## Installation

You can install via HACS (Custom repository) or manually.

### Option A: HACS (Recommended)
1. In Home Assistant, install HACS if you don’t already have it: https://hacs.xyz/
2. HACS → Integrations → three‑dot menu → Custom repositories.
3. Add this repository URL and select category “Integration”.
4. Find “Run‑Chicken” in HACS and click Install.
5. Restart Home Assistant when prompted.

### Option B: Manual
1. Copy the folder `custom_components/run_chicken` from this repository into your Home Assistant config directory: `<config>/custom_components/run_chicken`
2. Restart Home Assistant.

## Configuration

After installation and restart:

1. Go to Settings → Devices & Services → Add Integration.
2. Search for “Run‑Chicken”.
3. Follow the on‑screen steps to pair with your door over Bluetooth.

Notes:
- Keep the door powered and within Bluetooth range during setup.
- If your host has multiple Bluetooth adapters, you may need to ensure the correct adapter is enabled for Home Assistant.

## Entities and Controls

The integration creates entities to control and monitor the door. Depending on your setup, you should see:

- Switch: `switch.run_chicken_door` — Toggle to open/close the door.
- Binary sensor: `binary_sensor.run_chicken_door_open` — Reports whether the door is open.

Entity names and IDs may vary based on your device name and instance; use the UI to confirm.

## Features

 [x] Open / Close
 [ ] Battery level
 [ ] Temperature
 [ ] Brightness / light level 
 [ ] Additional diagnostics and improved pairing UX


## Development

This repository follows the general structure of a Home Assistant custom integration.

- Domain: `run_chicken`
- Source: `custom_components/run_chicken/`

Quick start (optional):
- Use the provided `scripts/develop` to spin up a local HA dev environment
- Linting: `scripts/lint`

See `CONTRIBUTING.md` for guidelines.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Acknowledgements

- Inspired by the Home Assistant integration blueprint and community examples
- Not affiliated with or endorsed by Run‑Chicken; all trademarks are the property of their respective owners
