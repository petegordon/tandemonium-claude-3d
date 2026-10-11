"""Goose-fit tandem, step 1: rider measurements from the dressed geese (rest pose, metres, Blender Z-up, -Y forward).

  blender -b --factory-startup --python scripts/measure_geese.py

Writes out/fit/geese_measure.json (both characters). Bone joints are the rig's rest heads; mesh extents use the
worn outfit (layered "__" sub-meshes skipped, as the game shows them).
"""
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "fit"
OUT.mkdir(parents=True, exist_ok=True)
CHARS = ("outfit_male", "outfit_female")


def verts(names):
    pts = []
    for n in names:
        o = bpy.data.objects.get(n)
        if o is not None and o.type == "MESH":
            v = np.array([x.co[:] for x in o.data.vertices])
            m = np.array(o.matrix_world)
            pts.append((m[:3, :3] @ v.T).T + m[:3, 3])
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def r(x):
    return round(float(x), 4)


report = {}
for ch in CHARS:
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{ch}-goose" / f"{ch}_dressed.blend"))
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    B = rig.data.bones
    j = {b.name: np.array(b.head_local[:]) for b in B}
    L = {b.name: b.length for b in B}
    worn = [o.name for o in bpy.data.objects if o.type == "MESH" and "__" not in o.name and o.parent is None]
    allv = verts(worn)
    body = verts(["body"])
    hip_mid = (j["LeftUpLeg"] + j["RightUpLeg"]) / 2
    sh_mid = (j["LeftArm"] + j["RightArm"]) / 2
    band = lambda v, z0, z1: v[(v[:, 2] > z0) & (v[:, 2] < z1)]
    legwear = verts([n for n in ("breeches", "skirt") if n in bpy.data.objects])
    seat_band = band(legwear, hip_mid[2] - 0.15, hip_mid[2] + 0.02)
    sh_band = band(allv, sh_mid[2] - 0.08, sh_mid[2] + 0.04)
    crotch = legwear[(np.abs(legwear[:, 0]) < 0.03) & (legwear[:, 2] < hip_mid[2])]
    boots = verts(["boots"])
    m = {
        "height_with_hat": r(allv[:, 2].max()),
        "height_head": r(body[:, 2].max()),
        "standing_height_head_from_sole": None,
        "hip_joint_z": r(hip_mid[2]),
        "hip_joint_y": r(hip_mid[1]),
        "hip_joint_width": r(j["LeftUpLeg"][0] - j["RightUpLeg"][0]),
        "crotch_z": r(crotch[:, 2].min()) if len(crotch) else None,
        "thigh": r(L["LeftUpLeg"]), "shin": r(L["LeftLeg"]), "leg": r(L["LeftUpLeg"] + L["LeftLeg"]),
        "ankle_z": r(j["LeftFoot"][2]),
        "ball_z": r(j["LeftToeBase"][2]),
        "ankle_to_ball": [r(x) for x in (j["LeftToeBase"] - j["LeftFoot"])],
        "boot_length": r(np.ptp(boots[boots[:, 0] > 0][:, 1])) if len(boots) else None,
        "sole_z": r(boots[:, 2].min()) if len(boots) else r(allv[:, 2].min()),
        "shoulder_joint_z": r(sh_mid[2]),
        "shoulder_joint_width": r(j["LeftArm"][0] - j["RightArm"][0]),
        "shoulder_mesh_width": r(np.ptp(sh_band[:, 0])),
        "seat_mesh_width": r(np.ptp(seat_band[:, 0])),
        "seat_mesh_depth": r(np.ptp(seat_band[:, 1])),
        "torso_hip_to_shoulder": r(np.linalg.norm(sh_mid - hip_mid)),
        "upper_arm": r(L["LeftArm"]), "forearm": r(L["LeftForeArm"]), "hand": r(L["LeftHand"]),
        "arm": r(L["LeftArm"] + L["LeftForeArm"]),
        "hip_to_head_top": r(body[:, 2].max() - hip_mid[2]),
        "joints": {n: [r(x) for x in j[n]] for n in ("Spine", "Spine1", "Spine2", "LeftArm", "LeftUpLeg")},
    }
    if bpy.data.objects.get("skirt"):
        sk = verts(["skirt"])
        m["skirt_hem_z"] = r(sk[:, 2].min())
        m["skirt_hem_width"] = r(np.ptp(band(sk, sk[:, 2].min(), sk[:, 2].min() + 0.05)[:, 0]))
        m["skirt_hem_depth"] = r(np.ptp(band(sk, sk[:, 2].min(), sk[:, 2].min() + 0.05)[:, 1]))
    m["standing_height_head_from_sole"] = r(m["height_head"] - m["sole_z"])
    report[ch] = m
    print("MEASURE", ch, json.dumps(m))
(OUT / "geese_measure.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("DONE")
