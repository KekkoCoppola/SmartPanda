# 🍓 SmartPanda — Raspberry Pi side

Everything in this folder runs on the Raspberry Pi wired to the car's OBD-II port via the Waveshare 2-CH CAN HAT. See the root [README](../README_EN.md) for wiring, hardware warnings, and the safety disclaimer.

## Contents

| Path | Purpose |
| :--- | :--- |
| `setup_can.sh` | Brings up `can0` (C-CAN, 500 kbps) and `can1` (B-CAN, 50 kbps) in listen-only mode. Requires root. |
| `requirements.txt` | Python deps: `python-can`, `cantools`, `isotp`. |
| `tools/sniff_events.py` | Event sniffer (NEW/CHG frames, 29-bit IDs included) for reverse engineering. |
| `tools/live_decode.py` | Live decoder for messages mapped in `../dbc/bcan.dbc`. |

Shared protocol knowledge lives at the repo root: `../dbc/` (DBC files) and `../docs/` (ID maps).

## Usage (on the Pi)

```bash
pip install -r raspberry/requirements.txt
chmod +x raspberry/setup_can.sh
./raspberry/setup_can.sh

python3 raspberry/tools/sniff_events.py --channel can0
python3 raspberry/tools/live_decode.py --channel can1
```
