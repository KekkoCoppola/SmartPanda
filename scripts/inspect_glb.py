#!/usr/bin/env python3
"""Inspect a GLB file: node hierarchy, meshes, materials, animations.

Usage:
    python scripts/inspect_glb.py [path/to/model.glb]
"""

import sys
from pathlib import Path

from pygltflib import GLTF2

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLB = REPO_ROOT / "assets" / "model" / "panda.glb"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GLB
    gltf = GLTF2().load(str(path))

    print(f"=== {path.name} ===")
    print(f"generator: {gltf.asset.generator!r}, version: {gltf.asset.version}")
    print(f"scenes={len(gltf.scenes)} nodes={len(gltf.nodes)} meshes={len(gltf.meshes)} "
          f"materials={len(gltf.materials)} animations={len(gltf.animations)} skins={len(gltf.skins)}")

    child_indices = {c for n in gltf.nodes for c in (n.children or [])}
    roots = [i for i in range(len(gltf.nodes)) if i not in child_indices]

    def describe(idx: int, depth: int) -> None:
        n = gltf.nodes[idx]
        bits = []
        if n.mesh is not None:
            mesh = gltf.meshes[n.mesh]
            mats = sorted({p.material for p in mesh.primitives if p.material is not None})
            bits.append(f"mesh#{n.mesh} {mesh.name!r} prims={len(mesh.primitives)} mats={mats}")
        if n.translation:
            bits.append(f"T={[round(v, 3) for v in n.translation]}")
        if n.rotation:
            bits.append(f"R={[round(v, 3) for v in n.rotation]}")
        if n.scale:
            bits.append(f"S={[round(v, 3) for v in n.scale]}")
        print("  " * depth + f"[{idx}] {n.name!r} " + " ".join(bits))
        for c in n.children or []:
            describe(c, depth + 1)

    print("\n--- node hierarchy ---")
    for r in roots:
        describe(r, 0)

    print("\n--- materials ---")
    for i, m in enumerate(gltf.materials):
        pbr = m.pbrMetallicRoughness
        base = pbr.baseColorFactor if pbr else None
        emis = m.emissiveFactor
        emis_tex = m.emissiveTexture is not None
        print(f"[{i}] {m.name!r} baseColor={base} emissiveFactor={emis} "
              f"emissiveTexture={emis_tex} alphaMode={m.alphaMode}")

    print("\n--- animations ---")
    if not gltf.animations:
        print("(none)")
    for i, a in enumerate(gltf.animations):
        print(f"[{i}] {a.name!r} channels={len(a.channels)} samplers={len(a.samplers)}")
        for ch in a.channels:
            t = ch.target
            node_name = gltf.nodes[t.node].name if t.node is not None else None
            print(f"    -> node[{t.node}] {node_name!r} path={t.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
