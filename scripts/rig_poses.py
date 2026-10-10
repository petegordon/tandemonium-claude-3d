"""Reference poses for the standard goose rig, shared by pose_test.py (deformation checks) and
make_anims.py (exported as one-frame "pose_*" clips). Poses are set from world-space bone
directions (aim) or bone-local rotations, so they work on any goose built with build_rig.py.
Rig conventions (see out/<char>-goose/<char>_rig.json): Jaw local -X opens; Tongue +X lifts;
EyelidUpper -X / EyelidLower +X close; Eye local Z yaws.
"""
import math

import bpy
from mathutils import Matrix, Vector


class Poser:
    def __init__(self, rig):
        self.rig = rig
        self.pbs = rig.pose.bones

    def reset(self):
        for pb in self.pbs:
            pb.rotation_mode = "XYZ"
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

    def aim(self, name, direction):
        """Rotate a bone (keeping its head) so it points along `direction` (armature space)."""
        pb = self.pbs[name]
        bpy.context.view_layer.update()
        cur = pb.matrix.copy()
        d = Vector(direction).normalized()
        R = cur.to_3x3().col[1].normalized().rotation_difference(d).to_matrix()
        new = (R @ cur.to_3x3()).to_4x4()
        new.translation = cur.translation
        pb.matrix = new
        bpy.context.view_layer.update()

    def rot(self, name, axis, deg):
        pb = self.pbs[name]
        pb.rotation_euler["XYZ".index(axis)] += math.radians(deg)
        bpy.context.view_layer.update()

    # ---- poses
    def t_pose(self):
        for s, sx in (("Left", 1), ("Right", -1)):
            self.aim(f"{s}Arm", (sx, 0, 0))
            self.aim(f"{s}ForeArm", (sx, 0, 0))
            self.aim(f"{s}Hand", (sx, 0, -0.15))

    def a_pose(self):
        for s, sx in (("Left", 1), ("Right", -1)):
            d = (sx * math.cos(math.radians(45)), 0, -math.sin(math.radians(45)))
            for b in ("Arm", "ForeArm", "Hand"):
                self.aim(f"{s}{b}", d)

    def riding(self):
        self.rot("Spine", "X", 8)
        self.rot("Spine1", "X", 6)
        for s, sx in (("Left", 1), ("Right", -1)):
            self.aim(f"{s}UpLeg", (sx * 0.12, -1.0, -0.25))
            self.aim(f"{s}Leg", (0, 0.15 if s == "Left" else -0.05, -1.0))
            self.aim(f"{s}Foot", (0, -1, -0.25))
            self.aim(f"{s}Arm", (sx * 0.25, -0.7, -0.45))
            self.aim(f"{s}ForeArm", (sx * 0.1, -1.0, -0.1))
            self.aim(f"{s}Hand", (0, -1, -0.3))

    def neck_curve(self):
        for n, deg in (("Neck", -12), ("Neck1", 10), ("Neck2", 16), ("Neck3", 10)):
            self.rot(n, "X", deg)
        self.rot("Head", "Y", 30)

    def honk_blink(self):
        self.rot("Jaw", "X", -26)
        self.rot("Tongue", "X", 15)
        for s in ("Left", "Right"):
            self.rot(f"{s}EyelidUpper", "X", -28)
            self.rot(f"{s}EyelidLower", "X", 16)
            self.rot(f"{s}Eye", "Z", 12)


POSES = ["t_pose", "a_pose", "riding", "neck_curve", "honk_blink"]
