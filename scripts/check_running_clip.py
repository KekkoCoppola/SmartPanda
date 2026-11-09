#!/usr/bin/env python3
"""Verify the baked 'running' clip in panda_rigged.glb.

Usage:
    python scripts/check_running_clip.py [path/to/model.glb]
"""

import sys
from pathlib import Path

import numpy as np
from pygltflib import GLTF2

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLB = REPO_ROOT / "assets" / "model" / "panda_rigged.glb"

CTYPE = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
         5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_accessor(gltf, blob, acc_idx):
    acc = gltf.accessors[acc_idx]
    bv = gltf.bufferViews[acc.bufferView]
    dtype = np.dtype(CTYPE[acc.componentType])
    ncomp = NCOMP[acc.type]
    start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    arr = np.frombuffer(blob, dtype=dtype, count=acc.count * ncomp, offset=start)
    return arr.reshape(acc.count, ncomp).copy()


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GLB
    gltf = GLTF2().load(str(path))
    blob = gltf.binary_blob()
    names = {n.name: i for i, n in enumerate(gltf.nodes) if n.name}
    failures = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'}  {msg}")
        if not cond:
            failures.append(msg)

    print(f"=== {path.name} ===")

    clips = {a.name: a for a in gltf.animations}
    check("running" in clips, "clip 'running' exists")
    for old in ("door_FL_open", "door_FR_open", "tailgate_open"):
        check(old in clips, f"clip {old!r} still present")
    if "running" not in clips:
        print(f"\nFAIL — {len(failures)} failure(s)")
        return 1
    running = clips["running"]

    # --- targets
    paths = {}
    for ch in running.channels:
        paths.setdefault(gltf.nodes[ch.target.node].name, set()).add(ch.target.path)
    for node_name in ("axle_front", "axle_rear"):
        check(paths.get(node_name) == {"rotation"}, f"{node_name} has a rotation channel")
    check(paths.get("body_shake") == {"rotation", "translation"},
          "body_shake has both a rotation and a translation channel")
    check(any(n and n.startswith("DesireFX.COM_Tube") for n in paths),
          "the exhaust holder is animated")

    # body_shake must sit directly above RootNode
    if "body_shake" in names:
        kids = gltf.nodes[names["body_shake"]].children or []
        check([gltf.nodes[k].name for k in kids] == ["RootNode"],
              "body_shake wraps RootNode")

    # --- wheel membership
    for axle in ("axle_front", "axle_rear"):
        if axle not in names:
            continue
        kids = [gltf.nodes[c].name or "" for c in (gltf.nodes[names[axle]].children or [])]
        check(len(kids) >= 8, f"{axle} groups {len(kids)} wheel parts (>=8)")
        check(not any("Support" in k for k in kids),
              f"{axle} does not include the brake caliper (Support)")
        z = gltf.nodes[names[axle]].translation[2]
        check((z > 0) == (axle == "axle_front"), f"{axle} pivot sits on the right axle (z={z:.1f})")

    # --- every sampler loops seamlessly
    for ch in running.channels:
        s = running.samplers[ch.sampler]
        vals = read_accessor(gltf, blob, s.output).astype(np.float64)
        first, last = vals[0], vals[-1]
        if ch.target.path == "rotation":
            same = abs(float(np.dot(first, last))) > 0.9999
        else:
            same = bool(np.allclose(first, last, atol=1e-6))
        check(same, f"{gltf.nodes[ch.target.node].name}.{ch.target.path} "
                    f"loops seamlessly (first == last)")

    # --- animated nodes must be TRS, not matrix
    for ch in running.channels:
        node = gltf.nodes[ch.target.node]
        check(node.matrix is None, f"{node.name} uses TRS, not a matrix")

    print(f"\n{'PASS' if not failures else 'FAIL'} — {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
