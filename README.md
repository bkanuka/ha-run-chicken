<div align="center">

# 🐔 ha-run-chicken 🐔

Home Assistant integration for the Run‑Chicken Automatic Chicken Door

</div>

## 🐔 Overview

`ha-run-chicken` is a custom Home Assistant component to control [Run‑Chicken](https://run-chicken.com/doors/t50/) automatic chicken coop doors via Bluetooth.
It has been tested with the T50 model (Bluetooth version) but should work with other Run‑Chicken Bluetooth models. The GIANT model is also supported; the door model is detected automatically from its Bluetooth advertisement.

This is a local push integration — it communicates directly with the door via Bluetooth and does not require cloud access or an internet connection.

### ⚠️ Note: This has only been tested by me, and will likely have bugs. Please report bugs so it can be improved!

## ✅️ Features

- Open and close control
- Report current door state (push)
- Local Bluetooth communication (no cloud required)

### 🤷‍♂️ Future Features:
- Battery level reporting
- Temperature and brightness reporting

### ⛔️ Out of Scope:
- Updating built-in schedule (e.g. automatic opening at sunrise)

Use the Run-Chicken app to set these schedules, or disable them in the app and use a Home Assistant automation instead.


## 📋️ Requirements

- A compatible Run‑Chicken door (tested on T50 with Bluetooth)
- A host with working Bluetooth (BLE) near the coop. Using a [Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy/) is **highly recommended**

## 🚀 Installation

You can install via HACS (Custom repository) or manually.

### ~~Option A: HACS (Recommended)~~ Not in HACS yet!
1. In Home Assistant, install HACS if you don’t already have it: https://hacs.xyz/
2. HACS → Integrations → three‑dot menu → Custom repositories.
3. Add this repository URL and select category “Integration”.
4. Find “Run‑Chicken” in HACS and click Install.
5. Restart Home Assistant when prompted.

### Option B: Manual
1. Copy the folder `custom_components/run_chicken` from this repository into your Home Assistant config directory: `<config>/custom_components/run_chicken`
2. Restart Home Assistant.

**Tip:** If you have the Terminal & SSH add-ons installed, `cd` to the `custom_components` directory and run:
```bash
wget -O - https://github.com/bkanuka/ha-run-chicken/archive/refs/heads/main.tar.gz | tar --strip-components=2 -zxf - ha-run-chicken-main/custom_components
```

## 🛠️ Setup

After installation and restart:

1. Go to Settings → Devices & Services → Add Integration.
2. Search for "Run‑Chicken".
3. Follow the on‑screen steps to pair with your door over Bluetooth.

Notes:
- Keep the door powered and within Bluetooth range during setup.
- If your host has multiple Bluetooth adapters, you may need to ensure the correct adapter is enabled for Home Assistant.

## 🐞 Debugging / Reporting Bugs

Because this integration has only been tested on a few doors, it's a huge help to capture the raw Bluetooth traffic when something doesn't work — especially on door models other than the T50.

To record it:

1. Go to **Settings → Devices & Services → Run‑Chicken → Configure**.
2. Turn on **"Record raw door data to a file"** and submit. The integration reloads automatically.
3. Reproduce the issue (open/close the door, wait for a state update, etc.).
4. Find the log file in your Home Assistant config folder, named `run_chicken_<address>.log` (e.g. `run_chicken_aabbccddeeff.log`). You can retrieve it with the File Editor or Samba add-on, or from the host shell under `/config`.
5. Attach the file to a [GitHub issue](https://github.com/bkanuka/ha-run-chicken/issues). **Turn the option back off** when you're done — it keeps appending while enabled.

Each line is a single message, formatted as `<UTC timestamp> <RX|TX> <base64 payload>`, where `RX` is data received from the door and `TX` is data sent to it. The bytes are base64-encoded so the file stays plain text and safe to paste.

## ✔️ To-Do

- [x] Open / Close control and reporting
- [ ] HACS integration
- [ ] Battery level reporting
- [ ] Temperature reporting (I think there is a sensor in the door)
- [ ] Brightness / light level reporting
- [ ] Additional diagnostics and improved pairing UX

## ⚖️ MIT License

This project is licensed under the MIT License. See `LICENSE` for details.

## 🫶 Acknowledgements

- Inspired by the Home Assistant integration blueprint and community examples
- Not affiliated with or endorsed by Run‑Chicken; all trademarks are the property of their respective owners

