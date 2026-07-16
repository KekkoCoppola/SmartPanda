#!/usr/bin/env python3
"""Rig assets/model/panda.glb for the SmartPanda status display.

The source model (Sketchfab FBX export) has every symmetric part (doors,
handles, windows, mirrors) fused left+right into a single mesh, no
animations, and all lamp meshes sharing one clearglass material.

This script produces assets/model/panda_rigged.glb:
  * splits the front-door part meshes into left/right by triangle X sign
  * groups each front door (+ its panel/handle/window/mirror) under a
    hinge pivot node, and the tailgate parts under a top-hinge pivot
  * adds glTF animation clips: door_FL_open, door_FR_open, tailgate_open
  * gives lamp meshes dedicated materials (mat_headlights, mat_taillights,
    mat_foglights, mat_indicators, mat_stoplight) so the app can drive
    their emissive at runtime

Usage:
    python scripts/rig_panda_glb.py
"""

import math
import sys
from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2,
    Accessor,
    Animation,
    AnimationChannel,
    AnimationChannelTarget,
    AnimationSampler,
    Attributes,
    BufferView,
    Material,
    Mesh,
    Node,
    PbrMetallicRoughness,
    Primitive,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "assets" / "model" / "panda.glb"
DST = REPO_ROOT / "assets" / "model" / "panda_rigged.glb"

PFX = "DesireFX.COM_"

# Model-local axes (RootNode space): X lateral, Y up, Z forward (+Z = hood).
# Which X sign is the car's LEFT side is verified visually; flip here if wrong.
LEFT_SIGN = -1  # local x < 0 => left (FL)

DOOR_OPEN_DEG = 65.0
TAILGATE_OPEN_DEG = 75.0
CLIP_SECONDS = 1.0

# Body color (sRGB hex), applied to the 'Fiat_Panda_2011_carpaint' material.
CARPAINT_HEX = "#84A9B2"


def srgb_to_linear(hex_color: str):
    def chan(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    h = hex_color.lstrip("#")
    return [chan(int(h[i:i + 2], 16)) for i in (0, 2, 4)]

CTYPE = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
         5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

IDENTITY3 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


def read_accessor(gltf, blob, acc_idx):
    acc = gltf.accessors[acc_idx]
    bv = gltf.bufferViews[acc.bufferView]
    dtype = np.dtype(CTYPE[acc.componentType])
    ncomp = NCOMP[acc.type]
    start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    tight = dtype.itemsize * ncomp
    stride = bv.byteStride or tight
    if stride == tight:
        arr = np.frombuffer(blob, dtype=dtype, count=acc.count * ncomp, offset=start)
        return arr.reshape(acc.count, ncomp).copy()
    out = np.empty((acc.count, ncomp), dtype=dtype)
    for i in range(acc.count):
        off = start + i * stride
        out[i] = np.frombuffer(blob, dtype=dtype, count=ncomp, offset=off)
    return out


class GlbBuilder:
    def __init__(self, gltf: GLTF2):
        self.gltf = gltf
        self.blob = bytearray(gltf.binary_blob())

    def _append(self, data: bytes) -> int:
        while len(self.blob) % 4:
            self.blob.append(0)
        offset = len(self.blob)
        self.blob.extend(data)
        return offset

    def add_accessor(self, array: np.ndarray, gl_type: str, component: int,
                     target, with_minmax: bool) -> int:
        data = np.ascontiguousarray(array).tobytes()
        offset = self._append(data)
        bv = BufferView(buffer=0, byteOffset=offset, byteLength=len(data))
        if target is not None:
            bv.target = target
        self.gltf.bufferViews.append(bv)
        acc = Accessor(
            bufferView=len(self.gltf.bufferViews) - 1,
            byteOffset=0,
            componentType=component,
            count=array.shape[0],
            type=gl_type,
        )
        if with_minmax:
            flat = array.reshape(array.shape[0], -1)
            acc.min = [float(v) for v in flat.min(axis=0)]
            acc.max = [float(v) for v in flat.max(axis=0)]
        self.gltf.accessors.append(acc)
        return len(self.gltf.accessors) - 1

    def finish(self):
        while len(self.blob) % 4:
            self.blob.append(0)
        self.gltf.set_binary_blob(bytes(self.blob))
        self.gltf.buffers[0].byteLength = len(self.blob)


def matrix_translation(node: Node):
    m = node.matrix
    if not m:
        return [0.0, 0.0, 0.0]
    if [round(v, 5) for v in m[:12]] != IDENTITY3:
        raise SystemExit(f"node {node.name!r}: matrix is not pure translation, abort")
    return [m[12], m[13], m[14]]


def find_holder(gltf, bare_name: str) -> int:
    for i, n in enumerate(gltf.nodes):
        if n.name == PFX + bare_name:
            return i
    raise SystemExit(f"holder node {bare_name!r} not found")


def geo_child(gltf, holder_idx: int) -> int:
    children = gltf.nodes[holder_idx].children or []
    if len(children) != 1:
        raise SystemExit(f"holder {gltf.nodes[holder_idx].name!r} has {len(children)} children")
    return children[0]


def split_mesh(gltf, blob, builder, mesh_idx: int):
    """Split a fused L+R mesh into (neg_x_mesh_idx, pos_x_mesh_idx, verts_neg, verts_pos)."""
    mesh = gltf.meshes[mesh_idx]
    if len(mesh.primitives) != 1:
        raise SystemExit(f"mesh {mesh.name!r}: expected 1 primitive")
    prim = mesh.primitives[0]
    pos = read_accessor(gltf, blob, prim.attributes.POSITION).astype(np.float32)
    idx = read_accessor(gltf, blob, prim.indices).reshape(-1, 3).astype(np.int64)

    tri_x = pos[idx].mean(axis=1)[:, 0]
    attr_names = [k for k, v in vars(prim.attributes).items()
                  if v is not None and not k.startswith("_")]
    attrs = {k: read_accessor(gltf, blob, getattr(prim.attributes, k)) for k in attr_names}

    results = []
    for side_name, mask in (("neg", tri_x < 0), ("pos", tri_x >= 0)):
        tris = idx[mask]
        used = np.unique(tris)
        remap = np.full(pos.shape[0], -1, dtype=np.int64)
        remap[used] = np.arange(used.shape[0])
        new_idx = remap[tris].astype(np.uint32).reshape(-1)

        new_attrs = Attributes()
        for name in attr_names:
            sub = np.ascontiguousarray(attrs[name][used])
            src_acc = gltf.accessors[getattr(prim.attributes, name)]
            acc_i = builder.add_accessor(
                sub, src_acc.type, src_acc.componentType,
                target=34962, with_minmax=(name == "POSITION"))
            setattr(new_attrs, name, acc_i)

        idx_i = builder.add_accessor(
            new_idx.reshape(-1, 1), "SCALAR", 5125, target=34963, with_minmax=False)

        new_mesh = Mesh(
            name=f"{mesh.name}_{side_name}",
            primitives=[Primitive(attributes=new_attrs, indices=idx_i,
                                  material=prim.material, mode=4)],
        )
        gltf.meshes.append(new_mesh)
        results.append((len(gltf.meshes) - 1, pos[used]))
    (mesh_neg, verts_neg), (mesh_pos, verts_pos) = results
    return mesh_neg, mesh_pos, verts_neg, verts_pos


def quat_y(deg):
    r = math.radians(deg) / 2
    return [0.0, math.sin(r), 0.0, math.cos(r)]


def quat_x(deg):
    r = math.radians(deg) / 2
    return [math.sin(r), 0.0, 0.0, math.cos(r)]


def add_clip(gltf, builder, name, node_idx, quat_open):
    times = np.array([[0.0], [CLIP_SECONDS]], dtype=np.float32)
    t_acc = builder.add_accessor(times, "SCALAR", 5126, target=None, with_minmax=True)
    quats = np.array([[0.0, 0.0, 0.0, 1.0], quat_open], dtype=np.float32)
    q_acc = builder.add_accessor(quats, "VEC4", 5126, target=None, with_minmax=False)
    gltf.animations.append(Animation(
        name=name,
        samplers=[AnimationSampler(input=t_acc, output=q_acc, interpolation="LINEAR")],
        channels=[AnimationChannel(
            sampler=0,
            target=AnimationChannelTarget(node=node_idx, path="rotation"))],
    ))


def main() -> int:
    gltf = GLTF2().load(str(SRC))
    blob = gltf.binary_blob()
    builder = GlbBuilder(gltf)
    root = 2  # 'RootNode'

    # The source top nodes combine to R_x(+90deg): car renders nose-down.
    # Replace them with a plain 0.01 scale (FBX cm -> m) so the car sits
    # wheels-down with X lateral, Y up, Z forward in world space too.
    # The translation (set below) grounds the wheels on y=0 and centers X/Z.
    gltf.nodes[0].matrix = None  # 'Sketchfab_model'

    # RootNode-space bbox of the whole car: holder translation + mesh extents
    gmin = np.full(3, np.inf)
    gmax = np.full(3, -np.inf)
    parent_of = {c: i for i, n in enumerate(gltf.nodes) for c in (n.children or [])}
    for idx, node in enumerate(gltf.nodes):
        if node.mesh is None:
            continue
        holder = gltf.nodes[parent_of[idx]] if idx in parent_of else None
        t = np.array(matrix_translation(holder) if holder else [0.0, 0.0, 0.0])
        for prim in gltf.meshes[node.mesh].primitives:
            acc = gltf.accessors[prim.attributes.POSITION]
            gmin = np.minimum(gmin, t + np.array(acc.min))
            gmax = np.maximum(gmax, t + np.array(acc.max))
    cx, cz = (gmin[0] + gmax[0]) / 2, (gmin[2] + gmax[2]) / 2
    ty, tx, tz = -0.01 * gmin[1], -0.01 * cx, -0.01 * cz
    gltf.nodes[1].matrix = [0.01, 0, 0, 0, 0, 0.01, 0, 0, 0, 0, 0.01, 0, tx, ty, tz, 1]
    print(f"grounding: bbox y_min={gmin[1]:.1f} -> lift {ty:.4f} m, "
          f"center offset x={tx:.4f} z={tz:.4f} m")

    # ---- front-door parts to split L/R: bare holder name -> role name
    door_parts = {
        "Door": "body",
        "Door_S": "panel",
        "DoorHandle": "handle",
        "DoorHandle_Key": "keylock",
        "Window": "window",
        "Back_Mirror_Base": "mirror_base",
        "Back_Mirror": "mirror",
        "Back_Mirror_Glas": "mirror_glass",
    }

    side_groups = {"neg": [], "pos": []}  # (holder_idx, translation)
    door_verts = {}

    for bare, role in door_parts.items():
        holder = find_holder(gltf, bare)
        geo = geo_child(gltf, holder)
        t = matrix_translation(gltf.nodes[holder])
        mesh_idx = gltf.nodes[geo].mesh
        m_neg, m_pos, v_neg, v_pos = split_mesh(gltf, blob, builder, mesh_idx)
        print(f"split {bare}: neg {v_neg.shape[0]}v / pos {v_pos.shape[0]}v  "
              f"t={[round(x, 1) for x in t]}")

        for side, m_idx in (("neg", m_neg), ("pos", m_pos)):
            n_geo = Node(name=f"{role}_{side}_geo", mesh=m_idx)
            gltf.nodes.append(n_geo)
            geo_i = len(gltf.nodes) - 1
            n_holder = Node(name=f"{role}_{side}", translation=list(t), children=[geo_i])
            gltf.nodes.append(n_holder)
            side_groups[side].append((len(gltf.nodes) - 1, t))
        if bare == "Door":
            door_verts["neg"] = (v_neg, t)
            door_verts["pos"] = (v_pos, t)

        gltf.nodes[root].children.remove(holder)

    # ---- hinge per side: front edge (max local Z) of the door body shell
    pivots = {}
    for side in ("neg", "pos"):
        verts, t = door_verts[side]
        zmax = float(verts[:, 2].max())
        edge = verts[verts[:, 2] > zmax - 2.0]
        hx = float(edge[:, 0].mean())
        hinge = [t[0] + hx, t[1], t[2] + zmax - 1.0]
        is_left = (1 if hx >= 0 else -1) == LEFT_SIGN
        pname = "door_FL" if is_left else "door_FR"
        children = []
        for holder_idx, ht in side_groups[side]:
            node = gltf.nodes[holder_idx]
            node.translation = [ht[0] - hinge[0], ht[1] - hinge[1], ht[2] - hinge[2]]
            node.name = f"{pname}_{node.name}"
            children.append(holder_idx)
        pivot = Node(name=pname, translation=hinge, children=children)
        gltf.nodes.append(pivot)
        pivots[pname] = len(gltf.nodes) - 1
        gltf.nodes[root].children.append(pivots[pname])
        print(f"{pname}: hinge at {[round(v, 1) for v in hinge]} "
              f"(side x{'<0' if side == 'neg' else '>=0'})")

    # ---- tailgate group (single central mesh, no splitting needed)
    tail_bare = ["Trunk", "Trunk_Chrom", "Trunk_Key", "Window3", "Window_Frame",
                 "LicPlate02_01", "LicPlate02_02", "LicPlate02_03", "LicPlate02_04"]
    trunk_holder = find_holder(gltf, "Trunk")
    trunk_geo = geo_child(gltf, trunk_holder)
    trunk_t = matrix_translation(gltf.nodes[trunk_holder])
    tpos = read_accessor(gltf, blob,
                         gltf.meshes[gltf.nodes[trunk_geo].mesh].primitives[0].attributes.POSITION)
    ymax = float(tpos[:, 1].max())
    top = tpos[tpos[:, 1] > ymax - 2.0]
    hinge = [trunk_t[0], trunk_t[1] + ymax - 1.0, trunk_t[2] + float(top[:, 2].mean())]
    children = []
    for bare in tail_bare:
        holder = find_holder(gltf, bare)
        t = matrix_translation(gltf.nodes[holder])
        node = gltf.nodes[holder]
        node.matrix = None
        node.translation = [t[0] - hinge[0], t[1] - hinge[1], t[2] - hinge[2]]
        node.name = f"tailgate_{bare.replace('LicPlate02_', 'plate')}"
        gltf.nodes[root].children.remove(holder)
        children.append(holder)
        print(f"tailgate part {bare}: t={[round(v, 1) for v in t]}")
    pivot = Node(name="tailgate", translation=hinge, children=children)
    gltf.nodes.append(pivot)
    pivots["tailgate"] = len(gltf.nodes) - 1
    gltf.nodes[root].children.append(pivots["tailgate"])
    print(f"tailgate: hinge at {[round(v, 1) for v in hinge]}")

    # ---- animation clips
    fl_sign = 1 if LEFT_SIGN < 0 else -1  # x<0 door swings +Y rotation outward
    add_clip(gltf, builder, "door_FL_open", pivots["door_FL"],
             quat_y(DOOR_OPEN_DEG * fl_sign))
    add_clip(gltf, builder, "door_FR_open", pivots["door_FR"],
             quat_y(-DOOR_OPEN_DEG * fl_sign))
    add_clip(gltf, builder, "tailgate_open", pivots["tailgate"],
             quat_x(TAILGATE_OPEN_DEG))

    # ---- dedicated lamp materials
    def clone_material(src_idx, name):
        src = gltf.materials[src_idx]
        pbr = src.pbrMetallicRoughness
        mat = Material(
            name=name,
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorFactor=list(pbr.baseColorFactor) if pbr and pbr.baseColorFactor else None,
                metallicFactor=pbr.metallicFactor if pbr else None,
                roughnessFactor=pbr.roughnessFactor if pbr else None,
            ),
            emissiveFactor=[0.0, 0.0, 0.0],
            alphaMode=src.alphaMode,
            doubleSided=src.doubleSided,
        )
        gltf.materials.append(mat)
        return len(gltf.materials) - 1

    lamp_map = {
        "HeadLamp_Lamp": "mat_headlights",
        "HeadLamp_Glass_Red": "mat_taillights",
        "Anti_Fog_Lamp": "mat_foglights",
        "Wing_Light_Lamp": "mat_indicators",
        "Stop_Light_Lamp": "mat_stoplight",
    }
    for bare, mat_name in lamp_map.items():
        holder = find_holder(gltf, bare)
        geo = geo_child(gltf, holder)
        prim = gltf.meshes[gltf.nodes[geo].mesh].primitives[0]
        prim.material = clone_material(prim.material, mat_name)
        print(f"{bare} -> {mat_name}")

    # ---- body color
    carpaint = next(m for m in gltf.materials if m.name == "Fiat_Panda_2011_carpaint")
    carpaint.pbrMetallicRoughness.baseColorFactor = srgb_to_linear(CARPAINT_HEX) + [1.0]
    print(f"carpaint -> {CARPAINT_HEX} "
          f"(linear {[round(v, 3) for v in carpaint.pbrMetallicRoughness.baseColorFactor]})")

    builder.finish()
    gltf.save(str(DST))
    print(f"\nsaved {DST} ({DST.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
