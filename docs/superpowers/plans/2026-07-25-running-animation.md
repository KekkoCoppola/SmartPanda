# Running Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a looping `running` clip to `panda_rigged.glb` that spins the four wheels, vibrates the exhaust, and shakes the whole vehicle, driveable from both the dev viewer and the Android app.

**Architecture:** The clip is baked into the GLB by `scripts/rig_panda_glb.py`, the same generator that already produces the door and tailgate clips. Wheels get one pivot per axle; the body gets a new node inserted above `RootNode`; the exhaust holder is animated directly. Every oscillation uses frequencies that are integer multiples of 1/duration, so the first and last keyframe coincide and the loop is seamless. Playback stays generic: the viewer uses `THREE.LoopRepeat`, the app advances `applyAnimation(index, elapsed % duration)`.

**Tech Stack:** Python 3.12 + `pygltflib` + `numpy` (generator), three.js 0.160 (viewer), Kotlin/Compose + SceneView/Filament (app).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-running-animation-design.md`. Any deviation must be agreed first.
- Model space is centimetres: 1 unit = 1 cm. Amplitudes in the spec are real units and must be converted (2.5 mm → 0.25 units).
- glTF: a node targeted by an animation must use TRS, never `matrix`. Convert with `node.matrix = None; node.translation = [...]` before animating it.
- glTF animations can target only translation / rotation / scale / morph weights. Never assume material animation.
- Loop-safety rule: for every sampler, the last output value must equal the first (rotations may differ by overall sign, which is the same rotation).
- Oscillation frequencies must be integer multiples of `1 / RUNNING_SECONDS`.
- `Support` / `Support1` (brake calipers) must NOT rotate with the wheels.
- Existing behaviour must not regress: clips `door_FL_open`, `door_FR_open`, `tailgate_open` keep working, lamp materials keep their names and mesh assignment.
- After every regeneration, `assets/model/panda_rigged.glb` must be copied to `android/app/src/main/assets/models/panda_rigged.glb`; the two files must be byte-identical (`md5sum` both).
- Run the generator with an interpreter that has `pygltflib`, `numpy`, `pillow` installed (`pip install -r scripts/requirements.txt`).
- **Repo state:** `scripts/rig_panda_glb.py`, both GLBs and `docs/model_map.md` already carry uncommitted work from the door-trim / headlight / tailgate fixes, on branch `main`. The commit steps below will therefore bundle that work unless it is committed or branched first. Confirm with the user before running any commit step.

---

### Task 1: Axle pivots and wheel rotation

**Files:**
- Modify: `scripts/rig_panda_glb.py`
- Create: `scripts/check_running_clip.py`
- Regenerate: `assets/model/panda_rigged.glb`, `android/app/src/main/assets/models/panda_rigged.glb`

**Interfaces:**
- Produces: constants `RUNNING_SECONDS`, `RUNNING_WHEEL_TURNS`, `RUNNING_SAMPLE_HZ`, `WHEEL_PREFIXES`, `WHEEL_EXCLUDE`; functions `group_axles(gltf, root) -> dict[str, int]` (axle name → pivot node index) and `add_running_clip(gltf, builder, targets)` where `targets` is a list of `(node_index, path, times_array, values_array)`.
- Consumes: existing helpers `find_holder`, `geo_child`, `matrix_translation`, `quat_x`, `GlbBuilder.add_accessor`.

- [ ] **Step 1: Write the failing check script**

Create `scripts/check_running_clip.py`:

```python
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
        print("\nFAILURES:", len(failures))
        return 1
    running = clips["running"]

    # --- targets
    targeted = {gltf.nodes[ch.target.node].name: ch.target.path for ch in running.channels}
    for node_name in ("axle_front", "axle_rear"):
        check(targeted.get(node_name) == "rotation", f"{node_name} has a rotation channel")

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
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/check_running_clip.py`
Expected: FAIL, `clip 'running' exists` reported as FAIL, exit code 1.

- [ ] **Step 3: Add the constants**

In `scripts/rig_panda_glb.py`, after the `INDICATOR_UPPER_FRAC` constant:

```python
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
```

- [ ] **Step 4: Add the axle grouping helper**

In `scripts/rig_panda_glb.py`, after `seam_z`:

```python
def group_axles(gltf, blob, root):
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
```

- [ ] **Step 5: Add the multi-channel clip builder**

In `scripts/rig_panda_glb.py`, after `add_clip`:

```python
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
```

- [ ] **Step 6: Wire the wheels into `main()`**

In `main()`, immediately before the `# ---- animation clips` section:

```python
    # ---- wheels: one pivot per axle, spun by the 'running' clip
    axles = group_axles(gltf, blob, root)
```

And immediately after the three existing `add_clip(...)` calls:

```python
    # ---- 'running': wheels spin a whole number of turns per loop. Keyframes
    # every 90 deg: a full turn as a single quaternion pair degenerates, since
    # 0 and 360 deg are the same rotation.
    steps = RUNNING_WHEEL_TURNS * 4
    spin_times = np.linspace(0.0, RUNNING_SECONDS, steps + 1)
    spin_quats = np.array([quat_x(360.0 * RUNNING_WHEEL_TURNS * i / steps)
                           for i in range(steps + 1)])
    running_targets = [
        (axles["axle_front"], "rotation", spin_times, spin_quats),
        (axles["axle_rear"], "rotation", spin_times, spin_quats),
    ]
    add_running_clip(gltf, builder, running_targets)
```

- [ ] **Step 7: Regenerate and sync the GLB**

```bash
python scripts/rig_panda_glb.py
cp assets/model/panda_rigged.glb android/app/src/main/assets/models/panda_rigged.glb
md5sum assets/model/panda_rigged.glb android/app/src/main/assets/models/panda_rigged.glb
```

Expected: the two md5 sums match, and the log lists `axle_front` / `axle_rear` with their part names — check by eye that `Support` is absent and that each axle lists 10-12 parts.

- [ ] **Step 8: Run the check script to verify it passes**

Run: `python scripts/check_running_clip.py`
Expected: PASS, 0 failures, exit code 0.

- [ ] **Step 9: Verify visually in the viewer**

Start the viewer (`preview_start` with `glb-viewer`, then navigate to `http://localhost:8000/scripts/view_rigged.html`) and step the clip manually, since looping playback does not exist yet:

```javascript
const A = window.__actions['running'];
A.action.reset(); A.action.play(); A.action.paused = true;
A.action.time = 0.125; window.__mixer.update(0);   // 45 deg into the first turn
```

Expected: all four wheels are rotated by the same angle, the brake calipers have not moved, nothing else has shifted.

- [ ] **Step 10: Commit** (only after confirming the repo-state caveat in Global Constraints)

```bash
git add scripts/rig_panda_glb.py scripts/check_running_clip.py assets/model/panda_rigged.glb android/app/src/main/assets/models/panda_rigged.glb
git commit -m "feat(model): spin the wheels with a looping running clip"
```

---

### Task 2: Body shake and exhaust vibration

**Files:**
- Modify: `scripts/rig_panda_glb.py`
- Modify: `scripts/check_running_clip.py`
- Modify: `docs/model_map.md`
- Regenerate: `assets/model/panda_rigged.glb`, `android/app/src/main/assets/models/panda_rigged.glb`

**Interfaces:**
- Consumes: `add_running_clip`, `RUNNING_SECONDS`, `RUNNING_SAMPLE_HZ` from Task 1.
- Produces: constants `SHAKE_ROT_DEG`, `SHAKE_TRANS_MM`, `EXHAUST_TRANS_MM`, `SHAKE_HARMONICS`, `EXHAUST_HARMONICS`; functions `loop_osc(t, harmonics, phase) -> np.ndarray` and `insert_shake_node(gltf, root) -> int`.

- [ ] **Step 1: Extend the check script with the new expectations**

In `scripts/check_running_clip.py`, after the `axle_front` / `axle_rear` target checks, add:

```python
    check(targeted.get("body_shake") in ("rotation", "translation"),
          "body_shake is animated")
    paths = {gltf.nodes[ch.target.node].name: set() for ch in running.channels}
    for ch in running.channels:
        paths[gltf.nodes[ch.target.node].name].add(ch.target.path)
    check(paths.get("body_shake") == {"rotation", "translation"},
          "body_shake has both a rotation and a translation channel")
    check(any(n and n.startswith("DesireFX.COM_Tube") for n in paths),
          "the exhaust holder is animated")

    # body_shake must sit directly above RootNode
    if "body_shake" in names:
        kids = gltf.nodes[names["body_shake"]].children or []
        check([gltf.nodes[k].name for k in kids] == ["RootNode"],
              "body_shake wraps RootNode")
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/check_running_clip.py`
Expected: FAIL on `body_shake is animated` and the exhaust check; the Task 1 checks still pass.

- [ ] **Step 3: Add the constants**

In `scripts/rig_panda_glb.py`, after `RUNNING_SAMPLE_HZ`:

```python
SHAKE_ROT_DEG = 0.15                 # roll and pitch amplitude
SHAKE_TRANS_MM = (1.0, 2.5, 0.0)     # lateral, vertical, longitudinal
EXHAUST_TRANS_MM = 1.5
SHAKE_HARMONICS = (2, 3, 5, 7, 11)   # Hz; integer multiples of 1/RUNNING_SECONDS
EXHAUST_HARMONICS = (11, 12)
```

- [ ] **Step 4: Add the oscillator and the shake node**

In `scripts/rig_panda_glb.py`, after `group_axles`:

```python
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
```

- [ ] **Step 5: Build the shake and exhaust channels**

In `main()`, replace the `running_targets = [...]` list from Task 1 with:

```python
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

    running_targets = [
        (axles["axle_front"], "rotation", spin_times, spin_quats),
        (axles["axle_rear"], "rotation", spin_times, spin_quats),
        (shake, "rotation", osc_times, shake_quats),
        (shake, "translation", osc_times, shake_trans),
        (tube, "translation", osc_times, tube_trans),
    ]
```

Note: an animated translation replaces the node's own translation, which is why `tube_base` is added back into every sample.

- [ ] **Step 6: Regenerate, sync, and run the check**

```bash
python scripts/rig_panda_glb.py
cp assets/model/panda_rigged.glb android/app/src/main/assets/models/panda_rigged.glb
python scripts/check_running_clip.py
```

Expected: PASS, 0 failures.

- [ ] **Step 7: Verify visually in the viewer**

```javascript
const A = window.__actions['running'];
A.action.reset(); A.action.play(); A.action.paused = false; A.action.setLoop(2201, Infinity);
```

Expected: wheels spin, the body has a small continuous tremor with no visible jump once per second, the exhaust vibrates. Compare against `A.action.paused = true; A.action.time = 0` for the rest pose.

- [ ] **Step 8: Update `docs/model_map.md`**

Add `running` to the clip table and a short section:

```markdown
| `running` (1 s, loop) | `axle_front`, `axle_rear`, `body_shake`, holder `Tube` | Veicolo in marcia | **Da mappare** |
```

```markdown
## Clip `running`

Ruote, scuotimento carrozzeria e vibrazione marmitta in un'unica clip da 1 s
pensata per il loop. Tutte le oscillazioni usano frequenze multiple intere di
1/durata, così primo e ultimo keyframe coincidono e il loop non ha scatti.

Le ruote fanno 4 giri per loop: con una circonferenza di 1,852 m sono ≈26,7
km/h apparenti. Per una velocità diversa si scala il tempo di riproduzione:
`timeScale = v_kmh / 26.7`.

`Support`/`Support1` (pinze freno) non stanno sotto i pivot assi: sul veicolo
reale non girano. Ampiezze regolabili con `SHAKE_ROT_DEG`, `SHAKE_TRANS_MM`,
`EXHAUST_TRANS_MM` in `scripts/rig_panda_glb.py`.
```

- [ ] **Step 9: Commit** (see the repo-state caveat)

```bash
git add scripts/rig_panda_glb.py scripts/check_running_clip.py docs/model_map.md assets/model/panda_rigged.glb android/app/src/main/assets/models/panda_rigged.glb
git commit -m "feat(model): add body shake and exhaust vibration to the running clip"
```

---

### Task 3: Viewer loop playback

**Files:**
- Modify: `scripts/view_rigged.html:70-92`

**Interfaces:**
- Consumes: the `running` clip from Task 2.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Make the looping clip a play/stop toggle**

In `scripts/view_rigged.html`, replace the whole `for (const clip of gltf.animations) { ... }` block (lines 70-92) with:

```javascript
  for (const clip of gltf.animations) {
    const looping = clip.name === 'running';
    const action = mixer.clipAction(clip);
    action.clampWhenFinished = !looping;
    action.setLoop(looping ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
    actions[clip.name] = { action, duration: clip.duration, open: false };
    const btn = document.createElement('button');
    btn.textContent = `${looping ? '⟳' : '▶'} ${clip.name}`;
    btn.onclick = () => {
      const st = actions[clip.name];
      st.open = !st.open;
      st.action.paused = false;
      if (looping) {
        // play/stop: a looping clip has no meaningful reverse
        if (st.open) { st.action.reset(); st.action.timeScale = 1; st.action.play(); }
        else { st.action.stop(); }
      } else if (st.open) {
        if (!st.action.isRunning()) { st.action.reset(); }
        st.action.timeScale = 1;
        st.action.play();
      } else {
        if (!st.action.isRunning()) { st.action.play(); st.action.time = st.duration; }
        st.action.timeScale = -1;
      }
      btn.classList.toggle('on', st.open);
    };
    ui.appendChild(btn);
  }
```

- [ ] **Step 2: Verify in the browser**

Reload `http://localhost:8000/scripts/view_rigged.html`, click `⟳ running`, and confirm with:

```javascript
JSON.stringify({
  loop: window.__actions['running'].action.loop,          // 2201 = LoopRepeat
  running: window.__actions['running'].action.isRunning(),
  doorLoop: window.__actions['door_FL_open'].action.loop,  // 2200 = LoopOnce
})
```

Expected: `loop: 2201`, `running: true`, `doorLoop: 2200`. Take a screenshot a second apart and confirm the wheels have turned. Click again and confirm the vehicle returns to rest. Open a door and confirm that clip still works.

- [ ] **Step 3: Commit** (see the repo-state caveat)

```bash
git add scripts/view_rigged.html
git commit -m "feat(viewer): loop the running clip with a play/stop toggle"
```

---

### Task 4: Android toggle

**Files:**
- Modify: `android/app/src/main/java/com/smartpanda/app/ui/VehicleScreen.kt`

**Interfaces:**
- Consumes: the `running` clip name from Task 2.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Add the clip constant**

In `VehicleScreen.kt`, after the `DOOR_CLIPS` declaration:

```kotlin
/** Looping clip: wheels, body shake and exhaust vibration (see docs/model_map.md). */
private const val RUNNING_CLIP = "running"

/** 1.0 plays the clip at its baked speed, ~26.7 km/h apparent. */
private const val RUNNING_SPEED_SCALE = 1f
```

- [ ] **Step 2: Add the state**

In `VehicleScreen`, right after the `doorProgress` declaration:

```kotlin
    val running = remember { mutableStateOf(false) }
```

- [ ] **Step 3: Advance the clip in the existing frame loop**

Replace the body of the `LaunchedEffect(modelNode) { ... }` block with:

```kotlin
    LaunchedEffect(modelNode) {
        val animator = modelNode.modelInstance.animator
        val indexByName = (0 until animator.animationCount)
            .associateBy { animator.getAnimationName(it) }
        var runningSeconds = 0f
        var lastFrameNanos = 0L
        while (isActive) {
            withFrameNanos { nanos ->
                val delta =
                    if (lastFrameNanos == 0L) 0f
                    else (nanos - lastFrameNanos) / 1_000_000_000f
                lastFrameNanos = nanos

                for ((clip, progress) in doorProgress) {
                    val index = indexByName[clip] ?: continue
                    animator.applyAnimation(
                        index,
                        progress.value * animator.getAnimationDuration(index),
                    )
                }

                indexByName[RUNNING_CLIP]?.let { index ->
                    val duration = animator.getAnimationDuration(index)
                    if (running.value) {
                        runningSeconds =
                            (runningSeconds + delta * RUNNING_SPEED_SCALE) % duration
                        animator.applyAnimation(index, runningSeconds)
                    } else if (runningSeconds != 0f) {
                        // settle back to the rest pose once, then stop touching it
                        runningSeconds = 0f
                        animator.applyAnimation(index, 0f)
                    }
                }

                animator.updateBoneMatrices()
            }
        }
    }
```

- [ ] **Step 4: Add the chip**

In the `LazyVerticalGrid` block, before `items(DOOR_CLIPS)`:

```kotlin
            item {
                var on by running
                FilterChip(
                    selected = on,
                    onClick = { on = !on },
                    label = { Text("In marcia") },
                )
            }
```

- [ ] **Step 5: Try to compile**

```bash
cd android && ./gradlew assembleDebug
```

Expected: the Gradle wrapper is git-ignored and generated by Android Studio on first sync, so this will most likely fail with "no such file or directory". If so, do not add a wrapper — record that the change is unverified by compilation and re-read the diff instead, checking: `mutableStateOf` / `remember` / `getValue` / `setValue` imports already present (they are, lines 17-20), `withFrameNanos` takes the frame time in nanoseconds, and `item {}` is a `LazyGridScope` member needing no import.

- [ ] **Step 6: Commit** (see the repo-state caveat)

```bash
git add android/app/src/main/java/com/smartpanda/app/ui/VehicleScreen.kt
git commit -m "feat(android): add an 'In marcia' toggle driving the running clip"
```

---

## Self-Review

**Spec coverage:** wheels → Task 1; body shake and exhaust → Task 2; loop-safety rule → check script, Tasks 1-2; speed semantics → documented in Task 2 step 8; viewer → Task 3; Android → Task 4; verification items 1-5 → check script plus the visual steps; smoke → correctly absent, dropped by decision.

**Placeholders:** none; every code step carries the actual code.

**Type consistency:** `add_running_clip(gltf, builder, targets)` is defined in Task 1 and used with the same 4-tuple shape in Task 2; `group_axles` returns the `axles` dict indexed as `axles["axle_front"]` in both tasks; `spin_times` / `spin_quats` created in Task 1 step 6 are still in scope where Task 2 step 5 reuses them; `RUNNING_CLIP` in Task 4 matches the clip name `running` created in Task 1.
