#!/usr/bin/env python3
"""Event sniffer for CAN reverse engineering.

Replacement for cansniffer without its 11-bit-only limitation: shows
NEW arbitration IDs and payload CHANGES, including 29-bit extended IDs
(which cansniffer silently drops — e.g. Fiat B-CAN lock/unlock frames).

Changed bytes are highlighted in red. Periodic messages that keep the
same payload print once and stay quiet afterwards.

Usage (on the Raspberry Pi, after ./setup_can.sh):
    python3 tools/sniff_events.py [--channel can1] [--ignore 180,5E0]

    --ignore  comma-separated hex IDs to mute (e.g. already-mapped ones)
"""

import argparse
import sys

import can

RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def fmt_id(msg: can.Message) -> str:
    if msg.is_extended_id:
        return f"{msg.arbitration_id:08X}x"
    return f"{msg.arbitration_id:03X} "


def fmt_data(data: bytes, previous) -> str:
    parts = []
    for i, byte in enumerate(data):
        if previous is not None and i < len(previous) and previous[i] != byte:
            parts.append(f"{RED}{byte:02X}{RESET}")
        else:
            parts.append(f"{byte:02X}")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="can1", help="SocketCAN interface (default: can1)")
    parser.add_argument("--ignore", default="", help="comma-separated hex IDs to mute")
    args = parser.parse_args()

    ignored = {int(x, 16) for x in args.ignore.split(",") if x.strip()}

    try:
        bus = can.Bus(channel=args.channel, interface="socketcan")
    except OSError as exc:
        print(f"Cannot open {args.channel}: {exc}. Did you run ./setup_can.sh?", file=sys.stderr)
        return 1

    last_data = {}
    start = None
    print(f"Listening on {args.channel}... NEW = first sighting, CHG = payload changed. Ctrl+C to stop.")
    try:
        for msg in bus:
            if msg.arbitration_id in ignored:
                continue
            if start is None:
                start = msg.timestamp
            key = (msg.arbitration_id, msg.is_extended_id)
            data = bytes(msg.data)
            previous = last_data.get(key)
            if previous == data:
                continue
            last_data[key] = data
            t = msg.timestamp - start
            if previous is None:
                tag = f"{DIM}NEW{RESET}"
            else:
                tag = f"{RED}CHG{RESET}"
            print(f"[{t:8.3f}] {tag} {fmt_id(msg)} [{msg.dlc}] {fmt_data(data, previous)}")
    except KeyboardInterrupt:
        print(f"\nStopped. {len(last_data)} distinct IDs seen.")
    finally:
        bus.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
