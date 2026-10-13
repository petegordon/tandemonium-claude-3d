"""Body landmarks (from OUR base rig) and per-garment SAM prompts / registration bands, shared by the garment tools.

LM[name] = (point(J, T) -> world xyz, allowed body regions); J / T = joint heads / tails (refs/key_views/joints.json).
PROMPTS[garment] = (positive landmark names, negative landmark names), or {"front"|"side"|"rear": (pos, neg)} when the
views need different prompts (prompts_for(garment, view) picks; side = left / right).
TRUST[garment] = world z bands (lo, hi) the garment never reaches: the drawn goose is registered to the mannequin there.
"""
import numpy as np

TORSO = ("torso_front", "torso_side", "torso_back")
LM = {
    # (the Head bone's head sits forward at the bill: head points hang off the top of the neck instead)
    "head_top": (lambda J, T: J["Neck3"] + np.array([0, -0.06, 0.23]), ("head",)),
    "head": (lambda J, T: J["Neck3"] + np.array([0, -0.06, 0.10]), ("head",)),
    "bill": (lambda J, T: J["Head"] + np.array([0, -0.05, 0.0]), ("head",)),
    "neck": (lambda J, T: J["Neck2"], ("neck",)),
    "neck_low": (lambda J, T: J["Neck"] + np.array([0, 0, -0.01]), ("neck", "torso_front", "torso_side")),
    "chest": (lambda J, T: J["Spine2"], TORSO),
    "chest_L": (lambda J, T: J["Spine2"] + np.array([0.11, 0, 0]), TORSO),
    "chest_R": (lambda J, T: J["Spine2"] + np.array([-0.11, 0, 0]), TORSO),
    "belly_L": (lambda J, T: J["Spine"] + np.array([0.12, 0, 0.05]), TORSO),
    "belly_R": (lambda J, T: J["Spine"] + np.array([-0.12, 0, 0.05]), TORSO),
    "belly": (lambda J, T: J["Spine"] + np.array([0, 0, 0.05]), TORSO),
    "hips": (lambda J, T: J["Hips"] + np.array([0, 0, 0.03]), TORSO),
    "chest_front": (lambda J, T: J["Spine2"] + np.array([0, -0.13, 0]), TORSO),
    "belly_front": (lambda J, T: J["Spine"] + np.array([0, -0.15, 0.05]), TORSO),
    "back": (lambda J, T: J["Spine2"] + np.array([0, 0.11, 0]), TORSO),
    "back_low": (lambda J, T: J["Spine"] + np.array([0, 0.12, 0.0]), TORSO),
    "seat": (lambda J, T: J["Hips"] + np.array([0, 0.16, -0.06]), TORSO + ("thigh",)),
    "tail": (lambda J, T: J["Hips"] + np.array([0, 0.22, -0.16]), TORSO + ("thigh",)),
    "skirt_L": (lambda J, T: J["Hips"] + np.array([0.15, 0, -0.10]), TORSO + ("thigh",)),
    "skirt_R": (lambda J, T: J["Hips"] + np.array([-0.15, 0, -0.10]), TORSO + ("thigh",)),
}
for _s in ("Left", "Right"):
    _k = _s[0]
    LM.update({
        f"upper_arm_{_k}": (lambda J, T, s=_s: (J[f"{s}Arm"] + J[f"{s}ForeArm"]) / 2, ("upper_arm",)),
        f"forearm_{_k}": (lambda J, T, s=_s: J[f"{s}ForeArm"] + 0.55 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm",)),
        f"forearm_hi_{_k}": (lambda J, T, s=_s: J[f"{s}ForeArm"] + 0.25 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm",)),
        f"wrist_{_k}": (lambda J, T, s=_s: J[f"{s}ForeArm"] + 0.95 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm", "hand")),
        f"hand_{_k}": (lambda J, T, s=_s: (J[f"{s}Hand"] + T[f"{s}Hand"]) / 2, ("hand",)),
        f"thigh_{_k}": (lambda J, T, s=_s: (J[f"{s}UpLeg"] + J[f"{s}Leg"]) / 2, ("thigh",)),
        f"knee_{_k}": (lambda J, T, s=_s: J[f"{s}Leg"] + np.array([0, 0, 0.05]), ("thigh", "shin")),
        f"shin_{_k}": (lambda J, T, s=_s: (J[f"{s}Leg"] + J[f"{s}Foot"]) / 2, ("shin",)),
        f"ankle_{_k}": (lambda J, T, s=_s: J[f"{s}Leg"] + 0.9 * (J[f"{s}Foot"] - J[f"{s}Leg"]), ("shin", "foot")),
        f"foot_{_k}": (lambda J, T, s=_s: (J[f"{s}Foot"] + J[f"{s}ToeBase"]) / 2, ("foot",)),
    })


def both(*names):
    return [f"{n}_{k}" for n in names for k in "LR"]


PROMPTS = {
    "hat": (["head_top"], ["bill", "neck", "chest"]),
    "bow_tie": (["neck_low"], ["head", "neck", "chest", "belly"]),
    "shirt": (["chest", "belly"] + both("upper_arm", "forearm"), ["head", "neck"] + both("thigh", "hand")),
    "vest": (["chest", "belly", "chest_L", "chest_R"], ["head", "neck"] + both("upper_arm", "forearm", "thigh")),
    # the jacket panel also wears the vest, shirt and bow tie: the open front (centre chest / belly) is NOT jacket
    "jacket": {"front": (["chest_L", "chest_R", "belly_L", "belly_R", "skirt_L", "skirt_R"] + both("upper_arm", "forearm"),
                         ["head", "neck", "chest", "belly"] + both("knee", "shin", "hand")),
               "side": (["back", "back_low", "seat"] + both("upper_arm", "forearm"),
                        ["head", "neck", "chest_front", "belly_front"] + both("knee", "shin", "hand")),
               "rear": (["back", "back_low", "chest_L", "chest_R", "skirt_L", "skirt_R"] + both("upper_arm", "forearm"),
                        ["head", "neck", "tail"] + both("knee", "shin", "hand"))},
    "glove": (both("hand", "wrist"), ["chest"] + both("forearm_hi", "upper_arm", "thigh")),
    "breeches": (["hips"] + both("thigh"), ["chest", "belly", "head"] + both("shin", "foot")),
    "boots": (both("shin", "ankle", "foot"), ["chest", "hips"] + both("thigh")),
}

TRUST = {
    "hat": [(0.0, 1.45)],
    "bow_tie": [(1.40, 1.75), (0.0, 0.60)],
    "shirt": [(1.40, 1.75), (0.0, 0.60)],
    "vest": [(1.40, 1.75), (0.0, 0.60)],
    "jacket": [(1.40, 1.75), (0.0, 0.35)],
    "glove": [(0.90, 1.75), (0.0, 0.60)],
    "breeches": [(1.05, 1.75)],
    "boots": [(0.45, 1.75)],
}


def prompts_for(garment, view):
    p = PROMPTS[garment]
    if isinstance(p, dict):
        return p["side" if view in ("left", "right") else view]
    return p
