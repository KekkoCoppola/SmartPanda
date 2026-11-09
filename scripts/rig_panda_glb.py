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

# License plate text (replaces the stock 3D "HUMSTER3D" lettering with a
# generated Italian-style plate texture on both plates).
PLATE_TEXT = "EA 273 EJ"

# Door rows to rig: (tag, {source holder: role name}, holder used for the hinge).
# Front doors carry their own window frame and mirrors; the rear ones are just
# the panel up to the belt line, their frame comes from the shared trim below.
DOOR_ROWS = [
    ("F", {
        "Door": "body",
        "Door_S": "panel",
        "DoorHandle": "handle",
        "DoorHandle_Key": "keylock",
        "Window": "window",
        "Back_Mirror_Base": "mirror_base",
        "Back_Mirror": "mirror",
        "Back_Mirror_Glas": "mirror_glass",
    }, "Door"),
    ("R", {
        "Door1": "body",
        "Door_S1": "panel",
        "DoorHandle1": "handle",
        "Window1": "window",
    }, "Door1"),
]

# Meshes worth decimating for the phone GPU: (prefix, target reduction,
# aggressiveness). Only standalone objects, with no shared border against a
# neighbouring panel, so simplifying one cannot open a seam. Body panels are
# left alone on purpose: they are what you actually look at, and they do share
# borders.
#
# Low aggressiveness makes the decimator stop early rather than wreck a shape.
#
# Two parts are deliberately absent, both checked by generating a build without
# them and comparing: the seats (overlapping thin shells self-intersect and
# speckle, even at 0.50) and the tyres (the tread is a ring of small blocks that
# merge into an irregular, jagged band — visible at any useful ratio, and they
# are on screen and rotating). Together they are 349 k triangles that this
# decimator cannot touch without it showing.
DECIMATE = [
    ("DashBoard", 0.50, 3),
    ("Disc", 0.50, 7),            # rims: thin spokes, stay conservative
    ("BrakeDisk", 0.70, 7),       # behind the rim
    ("Bolt", 0.70, 7),
    ("HeadLamp_Base", 0.80, 7),   # lamp housings, hidden behind the lenses
    ("HeadLamp_Lenses", 0.85, 7),
    ("Anti_Fog_Base", 0.85, 7),
    ("Anti_Fog_Lenses", 0.75, 7),
    ("Stop_Light_Base", 0.75, 7),
    ("Roof_Trunk", 0.60, 3),      # roof rails: part of the silhouette
]

# Black trim shared by both door rows: (holder, role name, mode). "split" cuts
# at the modelled seam, front section to the front doors and rear section to the
# rear ones; "front"/"rear" move the whole part to that row.
DOOR_TRIM = [
    ("Door_Plst", "molding", "split"),          # side band along the doors
    ("Frame_Window", "beltline", "split"),      # trim under the side windows
    ("Window_Frame3", "window_frame", "split"),  # window surround
    ("Window_Detail", "quarter_trim", "front"),  # quarter-window trim, front only
    # Both pillar segments belong to the rear door's window frame: the B-pillar
    # one closes its front edge, the C-pillar one its rear edge.
    ("Stoiki1", "pillar", "rear"),
    ("Stoiki1_S", "pillar_inner", "rear"),
]

# Front turn indicator inside the headlamp lens: outer/upper fraction of each
# lamp's bounding box that gets mat_indicators instead of mat_headlights.
INDICATOR_OUTER_FRAC = 0.33
INDICATOR_UPPER_FRAC = 0.40

# ---- "running" clip (vehicle in motion). Frequencies are integer multiples of
# 1/RUNNING_SECONDS so the first and last keyframe coincide and the loop is
# seamless. Amplitudes are real units; model space is centimetres.
RUNNING_SECONDS = 1.0
RUNNING_WHEEL_TURNS = 4      # per loop: 4 * 1.85 m circumference = 26.7 km/h
RUNNING_SAMPLE_HZ = 120      # sampling rate of the oscillatory channels

# Wheel parts, grouped per axle by the sign of their Z. 'Support' is the brake
# caliper: it is bolted to the hub carrier and must not spin.
WHEEL_PREFIXES = ("Disc", "Rubber", "BrakeDisk", "LogoWheel", "Bolt")
WHEEL_EXCLUDE = ("Support",)

SHAKE_ROT_DEG = 0.15                 # roll and pitch amplitude
SHAKE_TRANS_MM = (1.0, 2.5, 0.0)     # lateral, vertical, longitudinal
EXHAUST_TRANS_MM = 1.5
SHAKE_HARMONICS = (2, 3, 5, 7, 11)   # Hz; integer multiples of 1/RUNNING_SECONDS
EXHAUST_HARMONICS = (11, 12)


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


def load_prim(gltf, blob, mesh_idx: int):
    """Read the single primitive of a mesh: (prim, positions, tri indices, attrs)."""
    mesh = gltf.meshes[mesh_idx]
    if len(mesh.primitives) != 1:
        raise SystemExit(f"mesh {mesh.name!r}: expected 1 primitive")
    prim = mesh.primitives[0]
    pos = read_accessor(gltf, blob, prim.attributes.POSITION).astype(np.float32)
    idx = read_accessor(gltf, blob, prim.indices).reshape(-1, 3).astype(np.int64)
    attr_names = [k for k, v in vars(prim.attributes).items()
                  if v is not None and not k.startswith("_")]
    attrs = {k: read_accessor(gltf, blob, getattr(prim.attributes, k)) for k in attr_names}
    return prim, pos, idx, attr_names, attrs


def build_submesh(gltf, builder, prim, pos, idx, attr_names, attrs, mask, name):
    """Append a mesh holding only the triangles of `prim` selected by `mask`."""
    tris = idx[mask]
    used = np.unique(tris)
    remap = np.full(pos.shape[0], -1, dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    new_idx = remap[tris].astype(np.uint32).reshape(-1)

    new_attrs = Attributes()
    for aname in attr_names:
        sub = np.ascontiguousarray(attrs[aname][used])
        src_acc = gltf.accessors[getattr(prim.attributes, aname)]
        acc_i = builder.add_accessor(
            sub, src_acc.type, src_acc.componentType,
            target=34962, with_minmax=(aname == "POSITION"))
        setattr(new_attrs, aname, acc_i)

    idx_i = builder.add_accessor(
        new_idx.reshape(-1, 1), "SCALAR", 5125, target=34963, with_minmax=False)
    gltf.meshes.append(Mesh(
        name=name,
        primitives=[Primitive(attributes=new_attrs, indices=idx_i,
                              material=prim.material, mode=4)],
    ))
    return len(gltf.meshes) - 1, pos[used]


def split_mesh(gltf, blob, builder, mesh_idx: int):
    """Split a fused L+R mesh into (neg_x_mesh_idx, pos_x_mesh_idx, verts_neg, verts_pos)."""
    name = gltf.meshes[mesh_idx].name
    prim, pos, idx, attr_names, attrs = load_prim(gltf, blob, mesh_idx)
    tri_x = pos[idx].mean(axis=1)[:, 0]
    args = (gltf, builder, prim, pos, idx, attr_names, attrs)
    mesh_neg, verts_neg = build_submesh(*args, tri_x < 0, f"{name}_neg")
    mesh_pos, verts_pos = build_submesh(*args, tri_x >= 0, f"{name}_pos")
    return mesh_neg, mesh_pos, verts_neg, verts_pos


def seam_z(tri_lo, tri_hi, target):
    """Center of the triangle-free Z band nearest `target` (a modelled part seam).

    Used to cut a continuous strip mesh where the model already has a gap, so
    no triangle is torn in half by the cut plane.
    """
    order = np.argsort(tri_lo)
    lo, hi = tri_lo[order], tri_hi[order]
    reach = np.maximum.accumulate(hi)
    bands = [(reach[i], lo[i + 1]) for i in range(len(lo) - 1) if lo[i + 1] > reach[i]]
    if not bands:
        raise SystemExit("no triangle-free Z band found to cut on")
    a, b = min(bands, key=lambda band: abs((band[0] + band[1]) / 2 - target))
    return float(a + b) / 2


def group_axles(gltf, root):
    """Reparent the wheel parts under one pivot per axle.

    One pivot per axle rather than per wheel: left and right share Y and Z and
    spin the same way, and a pivot's X position does not affect a rotation
    about X. Returns {pivot name: node index}.
    """
    members = {"axle_front": [], "axle_rear": []}
    for holder in list(gltf.nodes[root].children):
        bare = (gltf.nodes[holder].name or "").replace(PFX, "")
        if not bare.startswith(WHEEL_PREFIXES) or bare.startswith(WHEEL_EXCLUDE):
            continue
        t = matrix_translation(gltf.nodes[holder])
        members["axle_front" if t[2] > 0 else "axle_rear"].append((holder, t))

    pivots = {}
    for axle, parts in members.items():
        # axle centre and radius from the tyre meshes, not hardcoded
        pts = []
        for holder, t in parts:
            if not (gltf.nodes[holder].name or "").replace(PFX, "").startswith("Rubber"):
                continue
            acc = gltf.accessors[gltf.meshes[gltf.nodes[geo_child(gltf, holder)].mesh]
                                 .primitives[0].attributes.POSITION]
            pts.extend([np.array(acc.min) + t, np.array(acc.max) + t])
        pts = np.array(pts)
        centre = [0.0, float((pts[:, 1].min() + pts[:, 1].max()) / 2),
                  float((pts[:, 2].min() + pts[:, 2].max()) / 2)]
        radius = float((pts[:, 1].max() - pts[:, 1].min()) / 2)

        children = []
        for holder, t in parts:
            node = gltf.nodes[holder]
            node.matrix = None
            node.translation = [t[0] - centre[0], t[1] - centre[1], t[2] - centre[2]]
            gltf.nodes[root].children.remove(holder)
            children.append(holder)
        gltf.nodes.append(Node(name=axle, translation=centre,
                               rotation=[0.0, 0.0, 0.0, 1.0], children=children))
        pivots[axle] = len(gltf.nodes) - 1
        gltf.nodes[root].children.append(pivots[axle])
        print(f"{axle}: centre {[round(v, 2) for v in centre]} r={radius:.2f}, "
              f"{len(children)} parts: "
              f"{sorted((gltf.nodes[c].name or '').replace(PFX, '') for c in children)}")
    return pivots


def loop_osc(t, harmonics, phase):
    """Sum of sines at integer frequencies: identical at t=0 and t=1."""
    out = np.zeros_like(t)
    for k, h in enumerate(harmonics):
        out += np.sin(2 * np.pi * h * t + phase + k * 1.7)
    return out / len(harmonics)


def insert_shake_node(gltf, root):
    """Insert an animatable TRS node directly above RootNode.

    RootNode's parent carries the cm->m scale in a matrix, which glTF forbids
    animating, so the shake gets a node of its own.
    """
    parent = next(i for i, n in enumerate(gltf.nodes) if root in (n.children or []))
    gltf.nodes.append(Node(name="body_shake", translation=[0.0, 0.0, 0.0],
                           rotation=[0.0, 0.0, 0.0, 1.0], children=[root]))
    shake = len(gltf.nodes) - 1
    gltf.nodes[parent].children = [shake if c == root else c
                                   for c in gltf.nodes[parent].children]
    print(f"body_shake inserted between node {parent} and RootNode")
    return shake


def make_plate_png(text: str) -> bytes:
    """Render an Italian-style license plate (white, blue side bands) as PNG."""
    import io

    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont

    w, h = 1040, 220
    img = PILImage.new("RGB", (w, h), "#F4F4F4")
    d = ImageDraw.Draw(img)
    band = 74
    d.rectangle([0, 0, band, h], fill="#003399")
    d.rectangle([w - band, 0, w, h], fill="#003399")
    d.rectangle([0, 0, w - 1, h - 1], outline="#111111", width=6)
    # EU stars (left band) + country letter
    import math
    cx, cy, rr = band // 2, 62, 24
    for k in range(12):
        a = k * math.pi / 6
        d.ellipse([cx + rr * math.sin(a) - 4, cy - rr * math.cos(a) - 4,
                   cx + rr * math.sin(a) + 4, cy - rr * math.cos(a) + 4], fill="#FFCC00")
    try:
        f_small = ImageFont.truetype("arialbd.ttf", 60)
        f_text = ImageFont.truetype("arialbd.ttf", 150)
    except OSError:
        f_small = f_text = ImageFont.load_default()
    d.text((cx, 160), "I", font=f_small, fill="white", anchor="mm")
    d.text(((w) // 2, h // 2 + 6), text, font=f_text, fill="#111111", anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def replace_plates(gltf, blob, builder):
    """Swap the stock 3D plate lettering for a textured quad with PLATE_TEXT.

    Keeps the white plate body (_04); removes lettering (_02), logo (_01)
    and blue band (_03); adds a quad 0.4 cm in front of the body, oriented
    by PCA of the body's vertices. Returns the bare holder name of the rear
    quad so it can join the tailgate group.
    """
    from pygltflib import Image as GltfImage
    from pygltflib import Sampler, Texture, TextureInfo

    png = make_plate_png(PLATE_TEXT)
    offset = builder._append(png)
    gltf.bufferViews.append(BufferView(buffer=0, byteOffset=offset, byteLength=len(png)))
    gltf.images.append(GltfImage(bufferView=len(gltf.bufferViews) - 1, mimeType="image/png"))
    gltf.samplers.append(Sampler(magFilter=9729, minFilter=9987, wrapS=33071, wrapT=33071))
    gltf.textures.append(Texture(sampler=len(gltf.samplers) - 1, source=len(gltf.images) - 1))
    gltf.materials.append(Material(
        name="mat_plate",
        pbrMetallicRoughness=PbrMetallicRoughness(
            baseColorTexture=TextureInfo(index=len(gltf.textures) - 1),
            metallicFactor=0.0, roughnessFactor=0.6),
        emissiveFactor=[0.0, 0.0, 0.0], alphaMode="OPAQUE"))
    plate_mat = len(gltf.materials) - 1

    root = 2
    rear_bare = None
    for prefix, tag in (("LicPlate01", "F"), ("LicPlate02", "R")):
        bg_holder = find_holder(gltf, f"{prefix}_04")
        t = matrix_translation(gltf.nodes[bg_holder])
        geo = geo_child(gltf, bg_holder)
        prim = gltf.meshes[gltf.nodes[geo].mesh].primitives[0]
        verts = read_accessor(gltf, blob, prim.attributes.POSITION).astype(np.float64)
        # Normal from PCA (smallest-variance axis), constrained to the Y/Z
        # plane: plates are symmetric about X, only tilted around it.
        evec = np.linalg.eigh(np.cov((verts - verts.mean(axis=0)).T)).eigenvectors
        n = evec[:, 0].copy()
        n[0] = 0.0
        n /= np.linalg.norm(n)
        outward = 1.0 if t[2] >= 0 else -1.0  # front plate faces +Z, rear -Z
        if n[2] * outward < 0:
            n = -n
        v = np.cross(n, [1.0, 0.0, 0.0])
        if v[1] < 0:
            v = -v
        u = np.cross(v, n)  # u x v == n
        # Extents and true geometric center from projection ranges (the
        # vertex-density mean is skewed toward the rounded corners).
        pu, pv, pn = (verts @ u), (verts @ v), (verts @ n)
        hu = float(pu.max() - pu.min()) / 2
        hv = float(pv.max() - pv.min()) / 2
        cq = (u * (pu.max() + pu.min()) / 2
              + v * (pv.max() + pv.min()) / 2
              + n * pn.max() + n * 0.4)
        quad = np.array([cq - u * hu + v * hv, cq + u * hu + v * hv,
                         cq - u * hu - v * hv, cq + u * hu - v * hv], dtype=np.float32)
        normals = np.tile(n.astype(np.float32), (4, 1))
        uvs = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=np.float32)
        idx = np.array([[0], [2], [1], [1], [2], [3]], dtype=np.uint32)

        attrs = Attributes(
            POSITION=builder.add_accessor(quad, "VEC3", 5126, 34962, True),
            NORMAL=builder.add_accessor(normals, "VEC3", 5126, 34962, False),
            TEXCOORD_0=builder.add_accessor(uvs, "VEC2", 5126, 34962, False),
        )
        gltf.meshes.append(Mesh(name=f"plate_{tag}_quad", primitives=[Primitive(
            attributes=attrs,
            indices=builder.add_accessor(idx, "SCALAR", 5125, 34963, False),
            material=plate_mat, mode=4)]))
        gltf.nodes.append(Node(name=f"plate_{tag}_geo", mesh=len(gltf.meshes) - 1))
        geo_i = len(gltf.nodes) - 1
        gltf.nodes.append(Node(
            name=f"{PFX}LicPlateTex_{tag}",
            matrix=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1],
            children=[geo_i]))
        holder_i = len(gltf.nodes) - 1
        gltf.nodes[root].children.append(holder_i)
        if tag == "R":
            rear_bare = "LicPlateTex_R"

        # drop lettering, logo and blue band; keep the white body (_04)
        for part in ("_01", "_02", "_03"):
            gltf.nodes[root].children.remove(find_holder(gltf, prefix + part))
        print(f"plate {tag}: quad {2 * hu:.1f}x{2 * hv:.1f} at {[round(x, 1) for x in t]}"
              f" n={[round(x, 2) for x in n]}")
    return rear_bare


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


def rig_door_row(gltf, blob, builder, root, tag, parts, shell_bare):
    """Split one row of doors L/R and hang each side off a hinge pivot.

    Returns (pivots, hinges, side_pivot, window_nodes, window_drop, shell_verts)
    where shell_verts maps side -> (vertices, holder translation) of the door
    shell, used later to place the trim cuts.
    """
    side_groups = {"neg": [], "pos": []}   # (holder index, translation)
    window_nodes = {}                      # side -> holder index, slid by the window clip
    window_drop = 0.0                      # glass height: how far it must sink
    shell = {}

    for bare, role in parts.items():
        holder = find_holder(gltf, bare)
        geo = geo_child(gltf, holder)
        t = matrix_translation(gltf.nodes[holder])
        m_neg, m_pos, v_neg, v_pos = split_mesh(gltf, blob, builder, gltf.nodes[geo].mesh)
        print(f"split {bare}: neg {v_neg.shape[0]}v / pos {v_pos.shape[0]}v  "
              f"t={[round(x, 1) for x in t]}")

        for side, m_idx, verts in (("neg", m_neg, v_neg), ("pos", m_pos, v_pos)):
            gltf.nodes.append(Node(name=f"{role}_{side}_geo", mesh=m_idx))
            geo_i = len(gltf.nodes) - 1
            gltf.nodes.append(Node(name=f"{role}_{side}", translation=list(t),
                                   children=[geo_i]))
            side_groups[side].append((len(gltf.nodes) - 1, t))
            if role == "window":
                window_nodes[side] = len(gltf.nodes) - 1
                window_drop = float(verts[:, 1].max() - verts[:, 1].min())
        if bare == shell_bare:
            shell["neg"] = (v_neg, t)
            shell["pos"] = (v_pos, t)

        gltf.nodes[root].children.remove(holder)

    # hinge per side: front edge (max local Z) of the door shell
    pivots, hinges, side_pivot = {}, {}, {}
    for side in ("neg", "pos"):
        verts, t = shell[side]
        zmax = float(verts[:, 2].max())
        edge = verts[verts[:, 2] > zmax - 2.0]
        hx = float(edge[:, 0].mean())
        hinge = [t[0] + hx, t[1], t[2] + zmax - 1.0]
        is_left = (1 if hx >= 0 else -1) == LEFT_SIGN
        pname = f"door_{tag}{'L' if is_left else 'R'}"
        children = []
        for holder_idx, ht in side_groups[side]:
            node = gltf.nodes[holder_idx]
            node.translation = [ht[0] - hinge[0], ht[1] - hinge[1], ht[2] - hinge[2]]
            node.name = f"{pname}_{node.name}"
            children.append(holder_idx)
        gltf.nodes.append(Node(name=pname, translation=hinge, children=children))
        pivots[pname] = len(gltf.nodes) - 1
        hinges[pname] = hinge
        side_pivot[side] = pname
        gltf.nodes[root].children.append(pivots[pname])
        print(f"{pname}: hinge at {[round(v, 1) for v in hinge]} "
              f"(side x{'<0' if side == 'neg' else '>=0'})")
    return pivots, hinges, side_pivot, window_nodes, window_drop, shell


def add_translate_clip(gltf, builder, name, node_idx, start, end):
    """Single-channel translation clip, same shape as add_clip but for sliding."""
    times = np.array([[0.0], [CLIP_SECONDS]], dtype=np.float32)
    t_acc = builder.add_accessor(times, "SCALAR", 5126, target=None, with_minmax=True)
    vals = np.array([start, end], dtype=np.float32)
    v_acc = builder.add_accessor(vals, "VEC3", 5126, target=None, with_minmax=False)
    gltf.animations.append(Animation(
        name=name,
        samplers=[AnimationSampler(input=t_acc, output=v_acc, interpolation="LINEAR")],
        channels=[AnimationChannel(
            sampler=0,
            target=AnimationChannelTarget(node=node_idx, path="translation"))],
    ))


def add_running_clip(gltf, builder, targets):
    """Build the looping 'running' clip from (node, path, times, values) tuples."""
    anim = Animation(name="running", samplers=[], channels=[])
    for node_idx, path, times, values in targets:
        t_acc = builder.add_accessor(
            np.asarray(times, dtype=np.float32).reshape(-1, 1), "SCALAR", 5126,
            target=None, with_minmax=True)
        v_acc = builder.add_accessor(
            np.asarray(values, dtype=np.float32),
            "VEC4" if path == "rotation" else "VEC3", 5126,
            target=None, with_minmax=False)
        anim.samplers.append(
            AnimationSampler(input=t_acc, output=v_acc, interpolation="LINEAR"))
        anim.channels.append(AnimationChannel(
            sampler=len(anim.samplers) - 1,
            target=AnimationChannelTarget(node=node_idx, path=path)))
    gltf.animations.append(anim)
    print(f"running: {len(anim.channels)} channels, {RUNNING_SECONDS}s loop")


def rig_door_trim(gltf, blob, builder, root, row_pivot, pivots, hinges, door_rear_z):
    """Hand each piece of the shared black trim to the door it belongs to.

    Every one of these parts is a single mesh shared by both sides (and mostly
    by both door rows), so left as-is it stays on the body and clips through an
    opening door. See DOOR_TRIM for the per-part mode.
    """
    for bare, role, mode in DOOR_TRIM:
        holder = find_holder(gltf, bare)
        t = matrix_translation(gltf.nodes[holder])
        geo = geo_child(gltf, holder)
        mesh_idx = gltf.nodes[geo].mesh
        mesh_name = gltf.meshes[mesh_idx].name
        prim, pos, idx, attr_names, attrs = load_prim(gltf, blob, mesh_idx)
        args = (gltf, builder, prim, pos, idx, attr_names, attrs)
        cen = pos[idx].mean(axis=1)
        if mode == "split":
            tri_z = pos[idx][:, :, 2]
            z_cut = seam_z(tri_z.min(axis=1), tri_z.max(axis=1), door_rear_z - t[2])
            on_front = cen[:, 2] > z_cut
        else:
            z_cut = None
            on_front = np.full(len(idx), mode == "front")

        groups = {}
        for side in ("neg", "pos"):
            on_side = (cen[:, 0] < 0) if side == "neg" else (cen[:, 0] >= 0)
            if mode != "rear":
                groups[row_pivot["F"][side]] = on_front & on_side
            if mode != "front":
                groups[row_pivot["R"][side]] = ~on_front & on_side

        assigned = np.zeros(len(idx), dtype=bool)
        for pname, mask in groups.items():
            assigned |= mask
            m_idx, _ = build_submesh(*args, mask, f"{mesh_name}_{pname}")
            gltf.nodes.append(Node(name=f"{role}_{pname}_geo", mesh=m_idx))
            geo_i = len(gltf.nodes) - 1
            h = hinges[pname]
            gltf.nodes.append(Node(
                name=f"{pname}_{role}",
                translation=[t[0] - h[0], t[1] - h[1], t[2] - h[2]],
                children=[geo_i]))
            gltf.nodes[pivots[pname]].children.append(len(gltf.nodes) - 1)
        rest = ~assigned
        if rest.any():
            m_rest, _ = build_submesh(*args, rest, f"{mesh_name}_body")
            gltf.nodes[geo].mesh = m_rest  # holder stays on the body, geometry shrinks
        else:
            gltf.nodes[root].children.remove(holder)
        cut = f"cut at local z={z_cut:.2f}" if z_cut is not None else "whole part"
        print(f"{role} ({bare}): {cut}, " +
              ", ".join(f"{p}={int(m.sum())}" for p, m in groups.items()) +
              f", body={int(rest.sum())}")


def rig_tailgate(gltf, blob, root, rear_plate):
    """Group the tailgate parts under a roof-line hinge; returns the pivot index.

    The hinge is taken over the whole group, i.e. the roof line where the
    tailgate meets the body. Using only the lower panel (Trunk) put it halfway
    up the car and the tailgate swung sideways instead of upwards.
    """
    tail_bare = ["Trunk", "Trunk_Chrom", "Trunk_Key", "Window3", "Window_Frame",
                 "LicPlate02_04", rear_plate,
                 "Stop_Light_Base", "Stop_Light_Lamp",          # third brake light
                 "Logo_Chrom_B", "Logo_Base_B", "Logo_Text1",   # FIAT badge
                 "Text_Panda",                                  # 'Panda' lettering
                 "Junitors_Back"]                               # rear wiper
    tail_pts = []
    for bare in tail_bare:
        if bare == rear_plate:
            continue  # generated quad: its vertices live in the new blob, and it
            # sits flush on LicPlate02_04, which is already in the list
        holder = find_holder(gltf, bare)
        t = np.array(matrix_translation(gltf.nodes[holder]))
        prim = gltf.meshes[gltf.nodes[geo_child(gltf, holder)].mesh].primitives[0]
        tail_pts.append(
            read_accessor(gltf, blob, prim.attributes.POSITION).astype(np.float64) + t)
    tail_pts = np.vstack(tail_pts)
    ymax = float(tail_pts[:, 1].max())
    top = tail_pts[tail_pts[:, 1] > ymax - 2.0]
    hinge = [0.0, ymax - 1.0, float(top[:, 2].mean())]

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
    gltf.nodes.append(Node(name="tailgate", translation=hinge, children=children))
    pivot = len(gltf.nodes) - 1
    gltf.nodes[root].children.append(pivot)
    print(f"tailgate: hinge at {[round(v, 1) for v in hinge]}")
    return pivot


def crease_normals(pos, idx, max_angle_deg=40.0):
    """Recompute normals after decimation while keeping hard edges.

    The source meshes split their vertices along creases — the tyre carries
    65,155 vertices for 17,520 distinct positions. Averaging every incident
    face welds those creases shut and the tread reads as blotchy shading, so a
    corner whose face normal departs too far from the averaged one gets its own
    copy of the vertex with the flat face normal.
    """
    pos = np.asarray(pos, dtype=np.float64)
    tri = pos[idx]
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    unit = face / np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-12)

    smooth = np.zeros(pos.shape)
    for corner in range(3):
        np.add.at(smooth, idx[:, corner], face)   # area weighted
    smooth /= np.maximum(np.linalg.norm(smooth, axis=1, keepdims=True), 1e-12)

    threshold = np.cos(np.radians(max_angle_deg))
    idx_out = idx.copy()
    extra_pos, extra_nrm = [], []
    next_id = len(pos)
    for corner in range(3):
        vertex = idx[:, corner]
        sharp = (unit * smooth[vertex]).sum(axis=1) < threshold
        if not sharp.any():
            continue
        count = int(sharp.sum())
        idx_out[sharp, corner] = np.arange(next_id, next_id + count)
        extra_pos.append(pos[vertex[sharp]])
        extra_nrm.append(unit[sharp])
        next_id += count

    normals = np.vstack([smooth] + extra_nrm) if extra_nrm else smooth
    if extra_pos:
        pos = np.vstack([pos] + extra_pos)
    return (np.ascontiguousarray(pos, dtype=np.float32),
            np.ascontiguousarray(idx_out, dtype=np.int64),
            np.ascontiguousarray(normals, dtype=np.float32))


def compact_scene(gltf):
    """Drop what the scene cannot reach and repack the buffer tightly.

    Two sources of dead weight in the app's asset: the rigging leaves the
    original fused holders and their meshes behind as orphans, and the source
    model carries UVs that no material samples (only the generated plate is
    textured). Everything is rewritten into a fresh, tightly packed buffer.
    """
    blob = gltf.binary_blob()
    before = len(blob)

    live = set()
    stack = list(gltf.scenes[gltf.scene or 0].nodes)
    while stack:
        i = stack.pop()
        if i in live:
            continue
        live.add(i)
        stack.extend(gltf.nodes[i].children or [])
    keep = sorted(live)
    node_map = {old: new for new, old in enumerate(keep)}

    textured = set()
    for i, m in enumerate(gltf.materials):
        pbr = m.pbrMetallicRoughness
        if ((pbr and (pbr.baseColorTexture or pbr.metallicRoughnessTexture))
                or m.normalTexture or m.emissiveTexture or m.occlusionTexture):
            textured.add(i)

    new_blob = bytearray()
    views, accs, acc_map = [], [], {}

    def copy_bytes(data):
        while len(new_blob) % 4:
            new_blob.append(0)
        offset = len(new_blob)
        new_blob.extend(data)
        return offset

    def copy_acc(old, target=None):
        if (old, target) in acc_map:
            return acc_map[(old, target)]
        arr = np.ascontiguousarray(read_accessor(gltf, blob, old))
        src = gltf.accessors[old]
        component = src.componentType
        # indices are uint32 throughout the source, but no mesh here reaches
        # 65536 vertices, so half of that is dead weight
        if target == 34963 and component == 5125 and int(arr.max(initial=0)) < 65536:
            arr = arr.astype(np.uint16)
            component = 5123
        data = arr.tobytes()
        bv = BufferView(buffer=0, byteOffset=copy_bytes(data), byteLength=len(data))
        if target is not None:
            bv.target = target
        views.append(bv)
        acc = Accessor(bufferView=len(views) - 1, byteOffset=0,
                       componentType=component, count=src.count, type=src.type,
                       min=src.min, max=src.max)
        accs.append(acc)
        acc_map[(old, target)] = len(accs) - 1
        return acc_map[(old, target)]

    def add_array(arr, gl_type, component, target, with_minmax=False):
        data = np.ascontiguousarray(arr).tobytes()
        bv = BufferView(buffer=0, byteOffset=copy_bytes(data), byteLength=len(data),
                        target=target)
        views.append(bv)
        acc = Accessor(bufferView=len(views) - 1, byteOffset=0,
                       componentType=component, count=arr.shape[0], type=gl_type)
        if with_minmax:
            flat = arr.reshape(arr.shape[0], -1)
            acc.min = [float(v) for v in flat.min(axis=0)]
            acc.max = [float(v) for v in flat.max(axis=0)]
        accs.append(acc)
        return len(accs) - 1

    live_meshes = sorted({gltf.nodes[i].mesh for i in keep if gltf.nodes[i].mesh is not None})
    mesh_map = {old: new for new, old in enumerate(live_meshes)}
    dropped_uv = 0
    tris_before = tris_after = 0
    meshes = []
    for old in live_meshes:
        bare = (gltf.meshes[old].name or "").replace(PFX, "")
        recipe = next(((r, a) for prefix, r, a in DECIMATE if bare.startswith(prefix)), None)
        prims = []
        for pr in gltf.meshes[old].primitives:
            if pr.indices is not None:
                tris_before += gltf.accessors[pr.indices].count // 3
            if recipe is not None and pr.indices is not None:
                import fast_simplification
                ratio, agg = recipe
                pos = read_accessor(gltf, blob, pr.attributes.POSITION).astype(np.float32)
                idx = read_accessor(gltf, blob, pr.indices).reshape(-1, 3).astype(np.uint32)
                pos, idx = fast_simplification.simplify(pos, idx, ratio, agg=agg)
                pos, idx, nrm = crease_normals(pos, np.asarray(idx, dtype=np.int64))
                attrs = Attributes(
                    POSITION=add_array(pos, "VEC3", 5126, 34962, with_minmax=True),
                    NORMAL=add_array(nrm, "VEC3", 5126, 34962))
                dtype = np.uint16 if idx.max(initial=0) < 65536 else np.uint32
                prims.append(Primitive(
                    attributes=attrs, material=pr.material, mode=pr.mode,
                    indices=add_array(idx.reshape(-1, 1).astype(dtype), "SCALAR",
                                      5123 if dtype is np.uint16 else 5125, 34963)))
                tris_after += len(idx)
                continue
            attrs = Attributes()
            for name, value in vars(pr.attributes).items():
                if value is None or name.startswith("_"):
                    continue
                if name == "TEXCOORD_0" and pr.material not in textured:
                    dropped_uv += 1
                    continue
                setattr(attrs, name, copy_acc(value, 34962))
            prims.append(Primitive(
                attributes=attrs, material=pr.material, mode=pr.mode,
                indices=copy_acc(pr.indices, 34963) if pr.indices is not None else None))
            if pr.indices is not None:
                tris_after += gltf.accessors[pr.indices].count // 3
        meshes.append(Mesh(name=gltf.meshes[old].name, primitives=prims))

    for image in gltf.images:
        if image.bufferView is None:
            continue
        src = gltf.bufferViews[image.bufferView]
        start = src.byteOffset or 0
        data = bytes(blob[start:start + src.byteLength])
        views.append(BufferView(buffer=0, byteOffset=copy_bytes(data), byteLength=len(data)))
        image.bufferView = len(views) - 1

    for anim in gltf.animations:
        for sampler in anim.samplers:
            sampler.input = copy_acc(sampler.input)
            sampler.output = copy_acc(sampler.output)
        anim.channels = [ch for ch in anim.channels if ch.target.node in node_map]
        for ch in anim.channels:
            ch.target.node = node_map[ch.target.node]

    nodes = []
    for old in keep:
        node = gltf.nodes[old]
        node.children = [node_map[c] for c in (node.children or []) if c in node_map] or None
        if node.mesh is not None:
            node.mesh = mesh_map[node.mesh]
        nodes.append(node)
    gltf.scenes[gltf.scene or 0].nodes = [
        node_map[i] for i in gltf.scenes[gltf.scene or 0].nodes if i in node_map]

    gltf.nodes, gltf.meshes = nodes, meshes
    gltf.accessors, gltf.bufferViews = accs, views
    while len(new_blob) % 4:
        new_blob.append(0)
    gltf.set_binary_blob(bytes(new_blob))
    gltf.buffers[0].byteLength = len(new_blob)
    print(f"compacted: {before / 1e6:.1f} -> {len(new_blob) / 1e6:.1f} MB "
          f"({len(gltf.nodes)} nodes, {len(gltf.meshes)} meshes, "
          f"{dropped_uv} unused UV sets dropped)")
    print(f"triangles: {tris_before:,} -> {tris_after:,} "
          f"({100 * (tris_before - tris_after) / tris_before:.0f}% removed)")


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

    # ---- doors: split each row L/R and hang it off a hinge pivot
    pivots, hinges = {}, {}
    row_pivot = {}      # tag -> {side: pivot name}
    row_windows = {}    # tag -> ({side: holder index}, drop distance)
    door_verts = {}     # front shell, used to place the trim cuts
    for tag, parts, shell_bare in DOOR_ROWS:
        p, h, side_pivot, win_nodes, win_drop, shell = rig_door_row(
            gltf, blob, builder, root, tag, parts, shell_bare)
        pivots.update(p)
        hinges.update(h)
        row_pivot[tag] = side_pivot
        row_windows[tag] = (win_nodes, win_drop)
        if tag == "F":
            door_verts = shell

    dverts, dt = door_verts["neg"]
    door_rear_z = dt[2] + float(dverts[:, 2].min())  # RootNode space
    rig_door_trim(gltf, blob, builder, root, row_pivot, pivots, hinges, door_rear_z)

    # ---- lamp materials (before the tailgate grouping renames holders)
    apply_lamp_materials(gltf, blob, builder)

    # ---- license plates: textured quads with PLATE_TEXT
    rear_plate = replace_plates(gltf, blob, builder)

    # ---- tailgate group. This renames the holders, so anything resolving
    # source names must run before it.
    pivots["tailgate"] = rig_tailgate(gltf, blob, root, rear_plate)

    # ---- wheels: one pivot per axle, spun by the 'running' clip
    axles = group_axles(gltf, root)

    # ---- animation clips
    fl_sign = 1 if LEFT_SIGN < 0 else -1  # x<0 door swings +Y rotation outward
    for tag, _parts, _shell in DOOR_ROWS:
        for side in ("neg", "pos"):
            pname = row_pivot[tag][side]
            sign = fl_sign if side == "neg" else -fl_sign
            add_clip(gltf, builder, f"{pname}_open", pivots[pname],
                     quat_y(DOOR_OPEN_DEG * sign))
    add_clip(gltf, builder, "tailgate_open", pivots["tailgate"],
             quat_x(TAILGATE_OPEN_DEG))

    # ---- windows: slide the glass straight down by its own height, so its top
    # ends below the belt line and it is hidden inside the door shell. The
    # holder is already a child of the door pivot, so a lowered window still
    # swings with an opening door instead of hanging in mid-air.
    for tag, (window_nodes, window_drop) in row_windows.items():
        for side, node_idx in window_nodes.items():
            base = list(gltf.nodes[node_idx].translation)
            pname = row_pivot[tag][side]              # door_FL / door_FR / door_RL / door_RR
            add_translate_clip(gltf, builder, f"window_{pname[-2:]}_down", node_idx,
                               base, [base[0], base[1] - window_drop, base[2]])
            print(f"window_{pname[-2:]}_down: drops {window_drop:.1f} units")

    # ---- 'running': wheels spin a whole number of turns per loop. Keyframes
    # every 90 deg: a full turn as a single quaternion pair degenerates, since
    # 0 and 360 deg are the same rotation.
    steps = RUNNING_WHEEL_TURNS * 4
    spin_times = np.linspace(0.0, RUNNING_SECONDS, steps + 1)
    spin_quats = np.array([quat_x(360.0 * RUNNING_WHEEL_TURNS * i / steps)
                           for i in range(steps + 1)])
    shake = insert_shake_node(gltf, root)
    tube = find_holder(gltf, "Tube")
    tube_base = matrix_translation(gltf.nodes[tube])
    gltf.nodes[tube].matrix = None
    gltf.nodes[tube].translation = list(tube_base)

    t = np.linspace(0.0, 1.0, int(RUNNING_SAMPLE_HZ * RUNNING_SECONDS) + 1)
    osc_times = t * RUNNING_SECONDS
    # roll about Z and pitch about X, composed exactly as q_roll * q_pitch
    roll = np.radians(SHAKE_ROT_DEG) * loop_osc(t, SHAKE_HARMONICS, 0.0) / 2
    pitch = np.radians(SHAKE_ROT_DEG) * loop_osc(t, SHAKE_HARMONICS, 1.1) / 2
    shake_quats = np.stack([np.cos(roll) * np.sin(pitch),
                            np.sin(roll) * np.sin(pitch),
                            np.sin(roll) * np.cos(pitch),
                            np.cos(roll) * np.cos(pitch)], axis=1)
    amp = np.array(SHAKE_TRANS_MM) / 10.0   # mm -> model units (cm)
    shake_trans = np.stack([amp[0] * loop_osc(t, SHAKE_HARMONICS, 0.6),
                            amp[1] * loop_osc(t, SHAKE_HARMONICS, 2.2),
                            amp[2] * loop_osc(t, SHAKE_HARMONICS, 3.4)], axis=1)
    tube_amp = EXHAUST_TRANS_MM / 10.0
    tube_trans = np.stack([tube_base[0] + tube_amp * loop_osc(t, EXHAUST_HARMONICS, 0.3),
                           tube_base[1] + tube_amp * loop_osc(t, EXHAUST_HARMONICS, 1.9),
                           np.full_like(t, tube_base[2])], axis=1)

    # An animated translation replaces the node's own, hence tube_base in every sample.
    running_targets = [
        (axles["axle_front"], "rotation", spin_times, spin_quats),
        (axles["axle_rear"], "rotation", spin_times, spin_quats),
        (shake, "rotation", osc_times, shake_quats),
        (shake, "translation", osc_times, shake_trans),
        (tube, "translation", osc_times, tube_trans),
    ]
    add_running_clip(gltf, builder, running_targets)

    # ---- body color
    carpaint = next(m for m in gltf.materials if m.name == "Fiat_Panda_2011_carpaint")
    carpaint.pbrMetallicRoughness.baseColorFactor = srgb_to_linear(CARPAINT_HEX) + [1.0]
    print(f"carpaint -> {CARPAINT_HEX} "
          f"(linear {[round(v, 3) for v in carpaint.pbrMetallicRoughness.baseColorFactor]})")

    builder.finish()
    compact_scene(gltf)
    gltf.save(str(DST))
    print(f"\nsaved {DST} ({DST.stat().st_size / 1e6:.1f} MB)")
    return 0


def apply_lamp_materials(gltf, blob, builder):
    """Give each driveable lamp its own material (must run before the tailgate
    grouping renames holders, since find_holder resolves source names)."""
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

    # The emissive material must sit on the outermost lens mesh: the '*_Lamp'
    # meshes are bulbs fully enclosed by their glass cover (opaque clearglass),
    # so lighting them up was never visible. Drive the lens instead.
    # Several meshes may share one material: the red rear lens and the third
    # brake light are both the stop lamp and must light together. The first
    # entry for a material decides its base colour, hence the red lens first.
    lamp_map = {
        "HeadLamp_Glas": "mat_headlights",
        "HeadLamp_Glass_Red": "mat_stoplight",
        "Stop_Light_Lamp": "mat_stoplight",
        "Anti_Fog_Glas": "mat_foglights",
        "Wing_LightGlas": "mat_indicators",
    }
    lamp_mats = {}
    for bare, mat_name in lamp_map.items():
        holder = find_holder(gltf, bare)
        geo = geo_child(gltf, holder)
        prim = gltf.meshes[gltf.nodes[geo].mesh].primitives[0]
        if mat_name in lamp_mats:
            prim.material = lamp_mats[mat_name]
        else:
            prim.material = clone_material(prim.material, mat_name)
            lamp_mats[mat_name] = prim.material
        print(f"{bare} -> {mat_name}")

    # ---- front turn indicators: on the real car the amber indicator is a
    # section of the headlamp unit itself, so split the outer/upper corner of
    # the lens off (both lamps) and drive it with mat_indicators.
    holder = find_holder(gltf, "HeadLamp_Glas")
    geo = geo_child(gltf, holder)
    mesh_idx = gltf.nodes[geo].mesh
    mesh_name = gltf.meshes[mesh_idx].name
    prim, pos, idx, attr_names, attrs = load_prim(gltf, blob, mesh_idx)
    args = (gltf, builder, prim, pos, idx, attr_names, attrs)
    cen = pos[idx].mean(axis=1)
    corner = np.zeros(len(idx), dtype=bool)
    for side in ("neg", "pos"):
        lamp = (cen[:, 0] < 0) if side == "neg" else (cen[:, 0] >= 0)
        lv = pos[idx[lamp]].reshape(-1, 3)
        x0, x1 = float(lv[:, 0].min()), float(lv[:, 0].max())
        y1, dy = float(lv[:, 1].max()), float(lv[:, 1].max() - lv[:, 1].min())
        span = INDICATOR_OUTER_FRAC * (x1 - x0)
        outer = (cen[:, 0] < x0 + span) if side == "neg" else (cen[:, 0] > x1 - span)
        corner |= lamp & outer & (cen[:, 1] > y1 - INDICATOR_UPPER_FRAC * dy)
    # Its own material, cloned from the lens it is cut out of: the app tints it
    # like the headlight when the indicator is off, so the lens reads as one
    # piece instead of showing a hole. Sharing mat_indicators would drag the
    # side repeaters and the rear band along with it.
    ind_mesh, _ = build_submesh(*args, corner, f"{mesh_name}_indicator")
    gltf.meshes[ind_mesh].primitives[0].material = clone_material(
        prim.material, "mat_indicator_front")
    main_mesh, _ = build_submesh(*args, ~corner, f"{mesh_name}_main")
    gltf.nodes[geo].mesh = main_mesh
    gltf.nodes.append(Node(name="headlamp_indicator_geo", mesh=ind_mesh))
    gltf.nodes[holder].children.append(len(gltf.nodes) - 1)
    print(f"headlamp indicator: {int(corner.sum())} tris -> mat_indicators, "
          f"{int((~corner).sum())} tris keep mat_headlights")

    # ---- rear turn indicator: the clear tail-light lens holds two bands, the
    # upper one is the indicator and the lower one the reversing light. Split
    # at the seam the model already has between them and drive only the upper
    # one. (seam_z takes triangle interval bounds, so it works on any axis.)
    holder = find_holder(gltf, "HeadLamp_Glass_White")
    geo = geo_child(gltf, holder)
    mesh_idx = gltf.nodes[geo].mesh
    mesh_name = gltf.meshes[mesh_idx].name
    prim, pos, idx, attr_names, attrs = load_prim(gltf, blob, mesh_idx)
    args = (gltf, builder, prim, pos, idx, attr_names, attrs)
    tri_y = pos[idx][:, :, 1]
    y_cut = seam_z(tri_y.min(axis=1), tri_y.max(axis=1), float(pos[:, 1].mean()))
    upper = pos[idx].mean(axis=1)[:, 1] > y_cut
    ind_mesh, _ = build_submesh(*args, upper, f"{mesh_name}_indicator")
    gltf.meshes[ind_mesh].primitives[0].material = lamp_mats["mat_indicators"]
    rest_mesh, _ = build_submesh(*args, ~upper, f"{mesh_name}_reverse")
    gltf.nodes[geo].mesh = rest_mesh
    gltf.nodes.append(Node(name="taillamp_indicator_geo", mesh=ind_mesh))
    gltf.nodes[holder].children.append(len(gltf.nodes) - 1)
    print(f"tail indicator: cut at local y={y_cut:.2f}, {int(upper.sum())} tris "
          f"-> mat_indicators, {int((~upper).sum())} tris stay clear (reversing light)")


if __name__ == "__main__":
    sys.exit(main())
