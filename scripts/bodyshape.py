"""Per-character body shape (D11) from a few symmetric sliders, shared by the outfit scripts.

chars/<char>.json:
  "body_shape": "base" (wear the shared base body) | "fitted" (its rig-fit) | "sliders" (below)
  "shape": {"arm_girth", "torso_girth", "hip_girth", "leg_girth", "leg_length", "height"}  (1.0 = base)

Sliders -> per-bone maps p -> head_new + A (p - head0) (the rig_fit.py transform format):
  arms (Arm, ForeArm, Hand)        girth across the bone, length 1
  torso (Spine, Spine1, Spine2)    torso_girth across; Hips hip_girth
  legs (UpLeg, Leg)                leg_girth across, leg_length along (the feet follow, unscaled);
                                   leg_pitch (degrees, + = feet further back) rotates each whole leg about its hip
  height                           uniform scale about the floor centre, applied last
Heads follow the chain: a child's head is its rest head carried by the parent's map.
"""
import json
from pathlib import Path

import numpy as np

DEFAULT = {"arm_girth": 1.0, "torso_girth": 1.0, "hip_girth": 1.0, "leg_girth": 1.0, "leg_length": 1.0,
           "height": 1.0, "leg_pitch": 0.0}


def frame(head, tail):
    y = tail - head
    y = y / np.linalg.norm(y)
    ref = np.array([0.0, 0.0, 1.0]) if abs(y[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = np.cross(y, ref)
    x /= np.linalg.norm(x)
    return np.stack([x, y, np.cross(x, y)], 1)


def slider_transforms(arm_obj, shape):
    """arm_obj: the base armature object. Returns {bone: {"head": [...], "A": [[...]]}} for every bone."""
    s = {**DEFAULT, **shape}
    out, rot = {}, {}
    for b in arm_obj.data.bones:                     # parents come before children
        n = b.name
        h0 = np.array(arm_obj.matrix_world @ b.head_local)
        t0 = np.array(arm_obj.matrix_world @ b.tail_local)
        g, length = 1.0, 1.0
        base = n.replace("Left", "").replace("Right", "")
        if base in ("Arm", "ForeArm", "Hand"):
            g = s["arm_girth"]
        elif base in ("Spine", "Spine1", "Spine2"):
            g = s["torso_girth"]
        elif base == "Hips":
            g = s["hip_girth"]
        elif base in ("UpLeg", "Leg"):
            g, length = s["leg_girth"], s["leg_length"]
        F = frame(h0, t0)
        R = rot[b.parent.name] if b.parent is not None else np.eye(3)   # children inherit the leg pitch
        if base == "UpLeg" and s["leg_pitch"]:
            a = np.radians(s["leg_pitch"])            # about +X: feet (below the hip) swing to +Y = back
            R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]]) @ R
        rot[n] = R
        A = R @ F @ np.diag([g, length, g]) @ F.T
        if b.parent is not None:
            p = out[b.parent.name]
            ph0 = np.array(arm_obj.matrix_world @ b.parent.head_local)
            head = np.array(p["head"]) + np.array(p["A"]) @ (h0 - ph0)
        else:
            head = h0
        out[n] = {"head": head.tolist(), "A": A.tolist()}
    k = s["height"]
    if k != 1.0:
        for v in out.values():
            v["head"] = (np.array(v["head"]) * k).tolist()
            v["A"] = (np.array(v["A"]) * k).tolist()
    return out


def body_transforms(root, char, arm_obj):
    """Transforms that turn the base body into the body this character wears (None = base body)."""
    root = Path(root)
    cfg = json.loads((root / "chars" / f"{char}.json").read_text())
    mode = cfg.get("body_shape", "base")
    if mode == "fitted":
        return json.loads((root / "out" / f"{char}-goose" / f"{char}_rigfit.json").read_text())["transforms"]
    if mode == "sliders":
        return slider_transforms(arm_obj, cfg.get("shape", {}))
    return None


def deform(V, W, names, arm_obj, transforms):
    """Linear-blend the per-bone maps over rest vertices V (n x 3) with weights W (n x bones)."""
    if not transforms:
        return V.copy()
    # weights over the armature's bones only: helper vertex groups (beak_lower, tongue) are not bones, and counting
    # them diluted the lower bill's Jaw weight -- with "height" != 1 the head moves and the bill lagged (beak open)
    bones = set(arm_obj.data.bones.keys())
    keep = np.array([n in bones for n in names], bool)
    W = np.where(keep[None, :], W, 0.0)
    s_ = W.sum(1, keepdims=True)
    W = np.where(s_ > 0, W / np.maximum(s_, 1e-9), W)
    out = V.copy()
    for i, n in enumerate(names):
        if n not in transforms:
            continue
        m = W[:, i] > 0
        if not m.any():
            continue
        h0 = np.array(arm_obj.matrix_world @ arm_obj.data.bones[n].head_local)
        tr = transforms[n]
        out[m] += W[m, i, None] * ((np.array(tr["head"]) + (V[m] - h0) @ np.array(tr["A"]).T) - V[m])
    return out
