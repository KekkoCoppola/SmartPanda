# 🐼 SmartPanda Project

> **Transforming a 2010 Fiat Panda (169) into a fully connected Smart Car.**

![Project Status](https://img.shields.io/badge/Status-In%20Development-yellow?style=for-the-badge)
![Hardware](https://img.shields.io/badge/Hardware-Raspberry%20Pi_4_%7C_Waveshare_CAN-red?style=for-the-badge&logo=raspberrypi)
![Protocol](https://img.shields.io/badge/Protocol-CAN%20Bus%20(ISO%2011898)-blue?style=for-the-badge)
![Language](https://img.shields.io/badge/Language-Python%203-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

## 📖 About The Project

**SmartPanda** is an open-source initiative to reverse-engineer and modernize the Fiat Panda 169 platform. By interfacing directly with the vehicle's CAN Bus networks (B-CAN and C-CAN), this project enables remote control via a mobile app, real-time telemetry, and smart automation.

**Target Vehicle:** Fiat Panda (Model 169) - Year 2010

<div align="center">
  <br />
  <img src="assets/img/target_vehicle.png" alt="Target Vehicle" width="300" />
  <br /><br />
</div>

---

## ⚡ Hardware & Requirements

### Hardware Components
*   **Core:** Raspberry Pi 3B+ / 4 (Running Raspberry Pi OS Lite)
*   **Interface:** Waveshare 2-CH CAN HAT (MCP2515 based) / CAN Bed
*   **Connection:** OBD-II to DB9 Cable / Custom Wiring harness
*   **Power:** 12V to 5V Step-Down Converter (3A min recommended)

### Software Prerequisites
*   Raspberry Pi OS (Lite recommended)
*   Python 3.7+
*   `can-utils` (for low-level debugging)

---

## 🔌 Wiring Schema (OBD-II to Waveshare HAT)

We tap into both the **C-CAN** (High Speed / Engine) and **B-CAN** (Low Speed / Body) networks.

| Signal | Fiat OBD Pin | Waveshare HAT Terminal | Network ID | Speed | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **VCC** | 16 | 12V | - | - | Power Source (Always On) |
| **GND** | 4 & 5 | GND | - | - | Signal & Chassis Ground |
| **CAN H** | 6 | H (CH 0) | `can0` | **500 kbps** | **C-CAN** (Engine, ABS, City) |
| **CAN L** | 14 | L (CH 0) | `can0` | **500 kbps** | **C-CAN** (Engine, ABS, City) |
| **LS-CAN L**| 1 | L (CH 1) | `can1` | **50 kbps** | **B-CAN** (Body, Lights, Doors) |
| **LS-CAN H**| 9 | H (CH 1) | `can1` | **50 kbps** | **B-CAN** (Body, Lights, Doors) |

> **⚠️ Warning:** Do NOT power the Raspberry Pi directly from the 12V OBD Pin unless you have a verified HAT with a wide-input voltage regulator. Most HATs only take 5V. Use a dedicated Step-Down converter!

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/yourusername/SmartPanda.git
cd SmartPanda
pip install -r requirements.txt
```

### 2. Configure CAN Interfaces

We have provided a script to automatically bring up the CAN interfaces with the correct bitrates.

```bash
chmod +x setup_can.sh
./setup_can.sh
```

*This sets `can0` to 500kbps (C-CAN) and `can1` to 50kbps (B-CAN).*

### 3. Verify Connection

Check if the interfaces are up and running:

```bash
ifconfig can0
ifconfig can1
```

---

## 🕵️ Reverse Engineering (Sniffing)

To identify specific packets (e.g., Door Open, Headlights On), use `candump` and `cansniffer` from the `can-utils` package.

**Example: Monitor Body Computer traffic (removing static IDs)**
```bash
cansniffer -c can1
```

Interact with the car (open a window, toggle lights) and watch for changing hex values!

---

## 🗺️ Roadmap

- [x] **Phase 0: Setup**
    - [x] Hardware Interface & Wiring
    - [x] OS Configuration & Network Up (`setup_can.sh`)
- [ ] **Phase 1: Decoding**
    - [ ] B-CAN ID Map (Doors, Lights, Windows)
    - [ ] C-CAN ID Map (RPM, Speed, Engine Temp)
- [ ] **Phase 2: Middleware**
    - [ ] Python Service for message parsing
    - [ ] Database integration (InfluxDB/SQLite)
- [ ] **Phase 3: User Interface**
    - [ ] Mobile App / Web Dashboard
- [ ] **Phase 4: Active Control**
    - [ ] Injecting messages to control windows/lights

---

## 🤝 Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated. 

Please verify your changes on a test bench if possible before submitting.

---

## ⚖️ Disclaimer

**USE AT YOUR OWN RISK.**

Modifying car electronics can be dangerous. The authors are not responsible for any damage to your vehicle, voided warranties, or accidents.
*   **Always test with the engine off and the car stationary.**
*   **Do not send active messages to the C-CAN (Engine/ABS) while driving.**
