# [EN]
# 🐼 SmartPanda Project
> **Transforming a 2010 Fiat Panda (169) into a fully connected Smart Car.**

![Project Status](https://img.shields.io/badge/Status-In%20Development-yellow?style=for-the-badge)
![Hardware](https://img.shields.io/badge/Hardware-Raspberry%20Pi%20%7C%20Waveshare%20CAN-red?style=for-the-badge)
![Protocol](https://img.shields.io/badge/Protocol-CAN%20Bus%20(ISO%2011898)-blue?style=for-the-badge)

## 📖 About The Project
**SmartPanda** is an open-source initiative to reverse-engineer and modernize the Fiat Panda 169 platform. By interfacing directly with the vehicle's CAN Bus networks (B-CAN and C-CAN), this project aims to enable remote control via a mobile app, real-time telemetry, and smart automation.

**Target Vehicle:** Fiat Panda (Model 169) - Year 2010
<div align="center">
  <br />
  <img src="src/main/webapp/img/Icon.png" alt="TecnoDeposit Logo" width="180" />
  <br /><br />
</div>
---

## ⚡ Hardware Architecture

### Components
* **Core:** Raspberry Pi (Running Raspberry Pi OS Lite)
* **Interface:** Waveshare 2-CH CAN HAT
* **Connection:** OBD-II Port (On-board diagnostics)

### 🔌 Wiring Schema (OBD-II to Waveshare HAT)
We tap into both the **C-CAN** (High Speed / Engine) and **B-CAN** (Low Speed / Body) networks.

| Signal | Fiat OBD Pin | Waveshare HAT Terminal | Network ID | Description |
| :--- | :---: | :---: | :---: | :--- |
| **VCC** | 16 | 12V | - | Power Source (Always On) |
| **GND** | 4 & 5 | GND | - | Signal & Chassis Ground |
| **CAN H** | 6 | H (CH 0) | `can0` | **C-CAN** (Engine, ABS, City) |
| **CAN L** | 14 | L (CH 0) | `can0` | **C-CAN** (Engine, ABS, City) |
| **LS-CAN L**| 1 | L (CH 1) | `can1` | **B-CAN** (Body, Lights, Doors) |
| **LS-CAN H**| 9 | H (CH 1) | `can1` | **B-CAN** (Body, Lights, Doors) |

> **⚠️ Warning:** Ensure your Waveshare HAT supports 12V input voltage before connecting Pin 16, or use an external step-down converter (12V -> 5V) to power the Raspberry Pi.

---

## 🛠️ Configuration & Setup

### 1. System Prep
Ensure `config.txt` is set up to enable SPI and the CAN controllers overlays (mcp2515).

### 2. Network Initialization
The Fiat Panda 169 operates on two distinct speeds. We configure the interfaces via SSH:

```bash
# C-CAN (High Speed - 500kbps) - Engine & Critical Systems
sudo ip link set can0 up type can bitrate 500000 listen-only on

# B-CAN (Low Speed - 50kbps) - Comfort & Body Systems
sudo ip link set can1 up type can bitrate 50000 listen-only on
```
### 3. Verification
Check if interfaces are up:
```bash
ifconfig can0
ifconfig can1
```
---

## 🕵️ Reverse Engineering Strategy (Sniffing)
To identify specific packets (e.g., Door Open, Headlights On), we use can-utils.
The bus is noisy. To find the signal in the noise:
1.  Connect to the B-CAN (can1) for body functions.
2.  Use cansniffer to filter out static static data.

```bash
#Monitor Body Computer traffic (removing static IDs)
cansniffer -c can1
```
Interact with the car (open a window, toggle lights) and watch for changing hex values!

---

## 🚀 Roadmap
[x] Hardware Interface & Wiring

[x] OS Configuration & Network Up

[ ] Phase 1: Decoding B-CAN ID Map (Doors, Lights, Windows)

[ ] Phase 2: Python Middleware for message parsing

[ ] Phase 3: Mobile App / Web Interface

[ ] Phase 4: Active Control (Injecting messages)

---

## 🤝 Contributing
Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

---

## ⚖️ Disclaimer
Modifying car electronics can verify dangerous. The authors are not responsible for any damage to your vehicle. Always test with the engine off and the car stationary.
