# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

SmartPanda is an early-stage, open-source hardware/software project to reverse-engineer and modernize the CAN bus network of a 2010 Fiat Panda (model 169), enabling remote control, telemetry, and automation via a Raspberry Pi.

The repository currently contains only setup tooling and documentation (`setup_can.sh`, `requirements.txt`, READMEs) — no application/decoding code has been written yet. Per the roadmap in `README_EN.md` / `README_IT.md`, Phase 0 (hardware interface + CAN network bring-up) is complete; Phase 1 (message decoding), Phase 2 (middleware/service), Phase 3 (UI), and Phase 4 (active control) are not yet started. Expect to build out this structure from scratch rather than find existing conventions to follow.

## Hardware/system context

This is not a typical software repo — code here runs on a Raspberry Pi (3B+/4, Raspberry Pi OS Lite) wired into the car's OBD-II port via a Waveshare 2-CH CAN HAT (MCP2515-based), and it interacts with **two physically distinct CAN networks**:

- `can0` = **C-CAN** (high-speed, 500 kbps) — engine, ABS, power steering. Safety-critical; per the README disclaimer, never inject/send messages here while driving.
- `can1` = **B-CAN** (low-speed, 50 kbps) — body computer, dashboard, lights, doors, windows.

Any code that talks to the bus needs to be written with this dual-network split in mind (separate interfaces, separate bitrates, separate risk profiles for read-only sniffing vs. active message injection).

## Commands

Bring up both CAN interfaces (must run on the actual Raspberry Pi hardware, requires root for `ip link`):
```bash
chmod +x setup_can.sh
./setup_can.sh
```
This sets `can0` to 500 kbps and `can1` to 50 kbps, both in `listen-only` mode.

Install Python dependencies:
```bash
pip install -r requirements.txt
```
Key dependencies: `python-can` (CAN bus I/O), `cantools` (DBC parsing/message decoding), `isotp` (ISO-TP transport for diagnostic/UDS-style messages).

Verify interfaces are up:
```bash
ifconfig can0
ifconfig can1
```

Reverse-engineer/sniff traffic (from `can-utils`, not a Python dependency — install via system package manager):
```bash
cansniffer -c can1   # e.g. to correlate body-computer actions (doors, lights, windows) with changing CAN IDs
candump can0          # raw dump of engine/ABS traffic
```

There is no build, lint, or test suite yet — when adding Python code, prefer conventions consistent with `python-can`/`cantools` usage patterns.

## Documentation

`README.md` is a language-selector stub; the substantive docs are in `README_EN.md` and `README_IT.md` (kept in sync, English and Italian). These contain the full wiring schema (OBD-II pin → CAN HAT terminal mapping) and safety disclaimer — consult them before making changes that touch hardware interfacing or wiring documentation.
