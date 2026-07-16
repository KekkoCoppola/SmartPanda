#!/usr/bin/env python3
"""Live decoder for mapped B-CAN messages.

Listens on can1 (B-CAN, 50 kbps) and prints decoded signal changes for
every message defined in dbc/bcan.dbc. Use it to verify the ID map
against the real car: toggle a light and check that the right signal
flips.

Usage (on the Raspberry Pi, after ./raspberry/setup_can.sh):
    python3 raspberry/tools/live_decode.py [--channel can1] [--dbc dbc/bcan.dbc]
"""

import argparse
import sys
from pathlib import Path

import can
import cantools

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="can1", help="SocketCAN interface (default: can1)")
    parser.add_argument("--dbc", default=str(REPO_ROOT / "dbc" / "bcan.dbc"), help="DBC file path")
    args = parser.parse_args()

    db = cantools.database.load_file(args.dbc)
    known_ids = {msg.frame_id: msg for msg in db.messages}
    print(f"Loaded {args.dbc}: {len(known_ids)} message(s) -> "
          + ", ".join(f"0x{fid:X} {m.name}" for fid, m in known_ids.items()))

    try:
        bus = can.Bus(channel=args.channel, interface="socketcan")
    except OSError as exc:
        print(f"Cannot open {args.channel}: {exc}. Did you run ./setup_can.sh?", file=sys.stderr)
        return 1

    last_decoded = {}
    print(f"Listening on {args.channel}... (Ctrl+C to stop)")
    try:
        for msg in bus:
            message_def = known_ids.get(msg.arbitration_id)
            if message_def is None:
                continue
            decoded = message_def.decode(msg.data)
            if decoded == last_decoded.get(msg.arbitration_id):
                continue
            previous = last_decoded.get(msg.arbitration_id, {})
            changes = {k: v for k, v in decoded.items() if previous.get(k) != v}
            last_decoded[msg.arbitration_id] = decoded
            raw = msg.data.hex(" ")
            print(f"[{msg.timestamp:.3f}] {message_def.name} (0x{msg.arbitration_id:X}) "
                  f"raw={raw} changed={changes}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        bus.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
