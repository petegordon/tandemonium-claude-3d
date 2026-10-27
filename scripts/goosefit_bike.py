"""Goose-fit tandem (docs/goose-fit-tandem.md): reshape the game's tandem to frame_fit.py's geometry.

Called by make_bike.py (--fit out/fit/frame_goosefit_<n>in.json) after the metres + D15 steps, before the pivots
are measured, so pivots / sockets / clips / decimation all follow the new shape. Every source mesh keeps its
name (D13); two tubes are added (goosefit_quill: bar riser in the stem; goosefit_stoker_stem: stoker bars on
the top tube) and the old stoker-bar gooseneck stub is cut off the frame.

Blender coordinates: forward -Y, up Z, x = rider's left. Spec points are (u forward from the captain BB, z).
- rigid groups (similarity: one scale + a move, x scaled too):
  front end (wheel, fork, mudguard, lamp, head tube) about the front hub, k = wheel / 0.7112;
  rear wheel + mudguard about the rear hub, k; saddles about their sit point, k; stoker bars about their grips, k;
  captain bars: front similarity, slid up the steer axis to the grip height (quill riser fills the gap), then
  bar + grips moved back to the fitted grip (goosefit_stem_ext: a swept-back stem from the stem clamp);
  cranks / chainrings / BB shells about the BB, kc = crank / 0.1581 in y-z (x kept); pedals ride the crank pin;
- chains: blend of the two end similarities along the chain;
- frame, top tube, stays, rack: k * v + inverse-distance blend of anchor offsets; anchors are sampled every
  ANCHOR_STEP along each tube's old centreline and its new one (seat tubes BB -> clamp, head tube, sloping
  top tube head -> captain seat tube -> stoker seat tube, down tube, boom, chainstay, seat stays, rack).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ANCHOR_STEP = 0.04
MUDGUARD_GAP = 0.012      # #505: mudguard and rack off the tread by this much
RACK = ["Cube", "Cube.002", "Cylinder.016"]   # carrier: leather pad, frame, clamp bolt (placed level on its own posts)
RACK_CLEAR = 0.015        # #505: carrier underside above the mudguard's outer skin
RACK_STAY_X = 0.05        # #505: rear carrier stays rise from the dropouts at this half-width
RACK_LEN = 1.5            # #505: the carrier is stretched along the bike so it reaches out over the wheel
MUDGUARD_STAYS = ["NurbsPath.014", "NurbsPath.015"]
MUDGUARD_TAIL_DEG = 25.0   # #505: the mudguard ends this far above horizontal behind the hub (clean cut)
IDW_P = 4
CRANK_OLD = 0.1581
GOOSENECK = {"y": (0.09, 0.26), "z_min": 0.86}       # old frame faces cut: captain-post stub that held the stoker bars

FRONT = ["NurbsPath.001", "NurbsPath.005", "Cylinder.006", "Cylinder.002", "Cylinder.003", "NurbsPath.004",
         "Cylinder.011", "Tee Joint"]
BARS = ["NurbsPath", "Cylinder.012", "Tee Joint.001", "Cylinder.017"]
REAR_EXTRA = ["Cylinder.009", "NurbsPath.014", "NurbsPath.015"]
SADDLE_C = ["seat", "Circle", "Cylinder.020", "Cylinder.021", "NurbsPath.010"]
SADDLE_S = ["seat.001", "Circle.001", "Cylinder.010", "Cylinder.023", "NurbsPath.011"]
STOKER_BARS = ["NurbsPath.009", "Cylinder.019"]
CHAINS = ["NurbsPath.007", "NurbsPath.008"]
WARP = ["Cylinder", "Cylinder.001", "NurbsPath.002", "NurbsPath.003", "NurbsPath.006"]
NEW_TUBES = {"goosefit_quill": "Steer", "goosefit_stoker_stem": "Bike_root", "goosefit_stem_ext": "Steer"}
BAR_ONLY = ["NurbsPath", "Cylinder.012"]           # bar + grips (the stem clamp Tee Joint.001 / Cylinder.017 stay)


def _o(n):
    return bpy.data.objects[n + "_cycle_0"]


def _v(n):
    return np.array([v.co[:] for v in _o(n).data.vertices])


def _set(n, V):
    _o(n).data.vertices.foreach_set("co", np.asarray(V, float).ravel())
    _o(n).data.update()


def _centre(ns):
    V = np.vstack([_v(n) for n in ns])
    c = (V.min(0) + V.max(0)) / 2
    c[0] = 0
    return c


def _seat_point(n):
    v = _v(n)
    top = v[v[:, 2] > v[:, 2].max() - 0.015]
    wide = top[np.abs(top[:, 0]) > 0.6 * np.abs(top[:, 0]).max()]
    return np.array([0.0, wide[:, 1].mean(), v[:, 2].max()])


def _sim(V, c_old, c_new, k, kx=None):
    out = c_new + (V - c_old) * k
    out[:, 0] = V[:, 0] * (k if kx is None else kx)
    return out


def _line_at_z(a, b, z):
    t = (z - a[2]) / (b[2] - a[2])
    return a + (b - a) * t


def _tube(name, p0, p1, r, uv, mat):
    bm = bmesh.new()
    d = Vector(p1) - Vector(p0)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r, depth=d.length)
    me = bpy.data.meshes.new(name + "_cycle_0")
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Translation((Vector(p0) + Vector(p1)) / 2) @
                 Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4())
    me.uv_layers.new(name="UVMap")
    for lp in me.uv_layers[0].data:
        lp.uv = uv
    me.materials.append(mat)
    me.shade_smooth()
    o = bpy.data.objects.new(name + "_cycle_0", me)
    bpy.context.scene.collection.objects.link(o)
    return o


def reshape(spec, groups):
    """spec: frame_fit.py's frame_*.json; groups: make_bike GROUPS (extended in place with the new tubes)."""
    P = spec["points"]
    W = spec["wheel_m"]
    k, kc = W / 0.7112, spec["crank_m"] / CRANK_OLD
    u_mid = (P["hub_F"][0] + P["hub_R"][0]) / 2

    def B(key):                                    # spec point -> Blender (x 0, y = -(u - u_mid), z)
        u, z = P[key]
        return np.array([0.0, -(u - u_mid), z])

    allnames = [n for g in groups.values() for n in g]
    cover = (FRONT + BARS + groups["Wheel_F"] + groups["Wheel_R"] + REAR_EXTRA + SADDLE_C + SADDLE_S + STOKER_BARS
             + CHAINS + WARP + RACK + groups["Crank_F"] + groups["Crank_R"] + ["wainframe_joint_low", "wainframe_joint_low.001"]
             + [n for g in ("Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR") for n in groups[g]])
    assert sorted(cover) == sorted(allnames), set(allnames) ^ set(cover)

    # ---- old anchors (current geometry) -------------------------------------------------------------
    hubF, hubR = _centre(["tyre_rear_low"]), _centre(["Cylinder.008"])
    bbF, bbR = _centre(["Gear.001"]), _centre(["Gear.002"])
    hv = _v("Tee Joint")
    zm = (hv[:, 2].min() + hv[:, 2].max()) / 2
    ring_lo, ring_hi = hv[hv[:, 2] < zm].mean(0), hv[hv[:, 2] >= zm].mean(0)
    ring_lo[0] = ring_hi[0] = 0
    axis = (ring_hi - ring_lo) / np.linalg.norm(ring_hi - ring_lo)
    seatC, seatS = _seat_point("seat"), _seat_point("seat.001")
    clampC, clampS = _centre(["Circle"]), _centre(["Circle.001"])
    gripC = _v("Cylinder.012").mean(0)
    gripC[0] = 0
    gripS = _v("Cylinder.019").mean(0)
    gripS[0] = 0
    sb = _v("NurbsPath.009")
    bar_clampS = sb[sb[:, 2] < sb[:, 2].min() + 0.01].mean(0)
    bar_clampS[0] = 0
    fr0 = _v("Cylinder")

    def tube_top(clamp):                           # seat-tube top: the post leans back from it to the clamp
        m = (fr0[:, 1] > clamp[1] - 0.12) & (fr0[:, 1] < clamp[1] + 0.02) & (fr0[:, 2] > 0.85)
        t = fr0[m].mean(0)
        t[0] = 0
        return t
    topC, topS = tube_top(clampC), tube_top(clampS)
    zt = _centre(["Cylinder.001"])[2]
    JH = _line_at_z(ring_lo, ring_hi, zt)
    JC = _line_at_z(bbF, topC, zt)
    JS = _line_at_z(bbR, topS, zt)
    rk = np.vstack([_v("Cube"), _v("Cube.002")])
    rack_rear = np.array([0.0, rk[:, 1].max(), rk[:, 2].mean()])

    # ---- new anchors ----------------------------------------------------------------------------------
    hubF2, hubR2, bbF2, bbR2 = B("hub_F"), B("hub_R"), B("bb_F"), B("bb_R")
    seatC2, seatS2, gripC2, gripS2 = B("saddle_C"), B("saddle_S"), B("grip_C"), B("grip_S")

    def Ff(V):
        return _sim(np.atleast_2d(V), hubF, hubF2, k)

    def Rr(V):
        return _sim(np.atleast_2d(V), hubR, hubR2, k)

    clampS2 = seatS2 + k * (clampS - seatS)
    topC2 = seatC2 + k * (topC - seatC)            # the saddle assembly is rigid: post + tube top move with it
    topS2 = seatS2 + k * (topS - seatS)
    JH2 = Ff(JH)[0]
    JC2 = topC2 + (bbF2 - topC2) / np.linalg.norm(bbF2 - topC2) * k * np.linalg.norm(topC - JC)
    JS2 = topS2 + (bbR2 - topS2) / np.linalg.norm(bbR2 - topS2) * k * np.linalg.norm(topS - JS)
    # the down tube (head -> stoker BB) crosses the captain seat tube: both must send that point to one place
    a, b, c, d = ring_lo[1:], bbR[1:], bbF[1:], topC[1:]
    M = np.array([b - a, -(d - c)]).T
    sd, tc = np.linalg.solve(M, c - a)
    X = ring_lo + (bbR - ring_lo) * sd
    X2 = bbF2 + (topC2 - bbF2) * tc
    tubes = [  # (old polyline, new polyline)
        ([bbF, bbR], [bbF2, bbR2]),                                   # boom
        ([bbF, X, JC, topC], [bbF2, X2, JC2, topC2]),                 # captain seat tube
        ([bbR, JS, topS], [bbR2, JS2, topS2]),                        # stoker seat tube
        ([ring_lo, JH, ring_hi], [Ff(ring_lo)[0], JH2, Ff(ring_hi)[0]]),   # head tube
        ([JH, JC, JS], [JH2, JC2, JS2]),                              # top tube (now sloping at the front)
        ([ring_lo, X, bbR], [Ff(ring_lo)[0], X2, bbR2]),              # down tube to the stoker BB
        ([bbR, hubR], [bbR2, hubR2]),                                 # chainstay
        ([hubR, topS], [hubR2, topS2]),                               # seat stays
    ]
    A_old, A_new = [], []
    for old, new in tubes:
        for (a, b), (a2, b2) in zip(zip(old[:-1], old[1:]), zip(new[:-1], new[1:])):
            n = max(2, int(np.linalg.norm(b - a) / ANCHOR_STEP) + 1)
            for t in np.linspace(0, 1, n):
                A_old.append(a + (b - a) * t)
                A_new.append(a2 + (b2 - a2) * t)
    A_old, A_new = np.array(A_old), np.array(A_new)
    OFF = A_new - k * A_old

    def warp(V):
        d = np.linalg.norm(V[:, None, 1:] - A_old[None, :, 1:], axis=2)
        w = 1.0 / (d ** IDW_P + 1e-10)
        out = k * V + (w[:, :, None] * OFF[None]).sum(1) / w.sum(1, keepdims=True)
        return out

    # ---- apply ------------------------------------------------------------------------------------------
    old = {n: _v(n) for n in allnames}
    for n in FRONT + groups["Wheel_F"]:
        _set(n, Ff(old[n]))
    d_bar = (gripC2[2] - Ff(gripC)[0][2]) / axis[2]
    for n in BARS:
        _set(n, Ff(old[n]) + axis * d_bar)
    grip_now = _v("Cylinder.012").mean(0)
    dy = gripC2[1] - grip_now[1]                    # + = back (Blender +Y)
    for n in BAR_ONLY:
        _set(n, _v(n) + np.array([0, dy, 0]))
    stem_top = _v("Tee Joint.001").mean(0)
    stem_top[0] = 0
    for n in groups["Wheel_R"] + REAR_EXTRA:
        _set(n, Rr(old[n]))
    for n in SADDLE_C:
        _set(n, _sim(old[n], seatC, seatC2, k))
    for n in SADDLE_S:
        _set(n, _sim(old[n], seatS, seatS2, k))
    for n in STOKER_BARS:
        _set(n, _sim(old[n], gripS, gripS2, k))
    for side, bb, bb2 in (("F", bbF, bbF2), ("R", bbR, bbR2)):
        for n in groups["Crank_" + side] + ["wainframe_joint_low" + ("" if side == "F" else ".001")]:
            _set(n, _sim(old[n], bb, bb2, kc, kx=1.0))
        for g in ("Pedal_" + side + "L", "Pedal_" + side + "R"):
            for n in groups[g]:
                c = (old[n].min(0) + old[n].max(0)) / 2
                c2 = bb2 + (c - bb) * kc
                c2[0] = c[0]
                _set(n, old[n] + (c2 - c))
    for n, (a, a2, ka), (b, b2, kb) in (("NurbsPath.007", (bbF, bbF2, kc), (bbR, bbR2, kc)),
                                        ("NurbsPath.008", (bbR, bbR2, kc), (hubR, hubR2, k))):
        V = old[n]
        t = np.clip((V[:, 1] - a[1]) / (b[1] - a[1]), 0, 1)[:, None]
        c_old, c_new, s = a + (b - a) * t, a2 + (b2 - a2) * t, ka + (kb - ka) * t
        V2 = c_new + (V - c_old) * s
        V2[:, 0] = V[:, 0]
        _set(n, V2)
    for n in WARP:
        _set(n, warp(old[n]))

    # ---- rear wheel clearance (#505) ---------------------------------------------------------------
    # Nothing but the wheel group may sit inside the rear tyre (the goosefit26 bike had the stays, rack,
    # clamp and frame foot in it, and the mudguard 8 mm into the tread). The hub moved back for that
    # (frame_fit CHAINSTAY_CLEAR); the mudguard is pushed out radially to MUDGUARD_GAP, and every other
    # part's clearance is reported so make_bike's log shows a regression at once.
    tyre = _v("Cylinder.008")
    rr = np.linalg.norm(tyre[:, 1:] - hubR2[1:], axis=1)
    R_t, r_in, half = rr.max(), rr.min(), np.abs(tyre[:, 0]).max()

    def tyre_dist(V):                              # signed distance from the tyre's solid, < 0 = inside
        r = np.linalg.norm(V[:, 1:] - hubR2[1:], axis=1)
        return np.maximum(np.abs(r - (R_t + r_in) / 2) - (R_t - r_in) / 2, np.abs(V[:, 0]) - half)

    # mudguard: concentric with the wheel (the source arc is not centred on the hub, so a push about the
    # hub left it tight at the front and 5 cm off at the tail), then its inner surface MUDGUARD_GAP off the
    # tread, thickness kept; the two mudguard stays are then stretched from the axle to meet it again
    mg = _v("Cylinder.009")
    yz = mg[:, 1:]
    A_ = np.c_[yz, np.ones(len(yz))]
    sol = np.linalg.lstsq(A_, (yz ** 2).sum(1), rcond=None)[0]      # Kasa circle fit: y^2+z^2 = a y + b z + c
    c_fit = sol[:2] / 2
    mudguard_recentre = float(np.linalg.norm(hubR2[1:] - c_fit))
    yz = yz + (hubR2[1:] - c_fit)
    r_mg = np.linalg.norm(yz - hubR2[1:], axis=1)
    mudguard_push = float(R_t + MUDGUARD_GAP - r_mg.min())
    yz = hubR2[1:] + (yz - hubR2[1:]) * ((r_mg + mudguard_push) / r_mg)[:, None]
    mg[:, 1:] = yz
    _set("Cylinder.009", mg)
    # the tail: the source strip flares sideways in its last few centimetres (a hook from above); cut it
    # clean on a plane through the hub, MUDGUARD_TAIL_DEG above horizontal behind the wheel
    o_mg = _o("Cylinder.009")
    bm = bmesh.new()
    bm.from_mesh(o_mg.data)
    t = math.tan(math.radians(MUDGUARD_TAIL_DEG))
    co, no = Vector((0, hubR2[1], hubR2[2])), Vector((0, -t, 1)).normalized()
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=co, plane_no=no)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if (v.co - co).dot(no) < -1e-6], context="VERTS")
    bm.to_mesh(o_mg.data)
    bm.free()
    o_mg.data.update()
    mg = _v("Cylinder.009")
    r_mg_in = float(np.linalg.norm(mg[:, 1:] - hubR2[1:], axis=1).min())
    for n in MUDGUARD_STAYS:
        V = _v(n)
        r = np.linalg.norm(V[:, 1:] - hubR2[1:], axis=1)
        f = (r_mg_in + 0.004) / r.max()                       # far end just inside the mudguard's inner skin
        V[:, 1:] = hubR2[1:] + (V[:, 1:] - hubR2[1:]) * f
        _set(n, V)
    # ---- carrier rack (#505, Pete: "a bit higher from a new frame post so that it goes straight out over the
    # rear tire and mudguard") ---------------------------------------------------------------------------
    # The source carrier, scaled k, placed LEVEL with its underside RACK_CLEAR above the mudguard's outer skin
    # and its front just behind the stoker's seat clamp; a stub post from the clamp carries the front, two
    # stays from the dropouts carry the rear (tubes made with the frame's paint below).
    rk_old = np.vstack([old[n] for n in RACK])
    c_old = (rk_old.min(0) + rk_old.max(0)) / 2
    size = (rk_old.max(0) - rk_old.min(0)) * k * np.array([1.0, RACK_LEN, 1.0])
    r_mg_out = float(np.linalg.norm(mg[:, 1:] - hubR2[1:], axis=1).max())
    rack_bottom = hubR2[2] + r_mg_out + RACK_CLEAR
    c_new = np.array([0.0, clampS2[1] + 0.03 + size[1] / 2, rack_bottom + size[2] / 2])
    for n in RACK:
        _set(n, c_new + (old[n] - c_old) * k * np.array([1.0, RACK_LEN, 1.0]))
    rk = np.vstack([_v(n) for n in ("Cube", "Cube.002")])
    rack_front = np.array([0.0, rk[:, 1].min() + 0.015, rk[:, 2].min() + 0.006])
    rack_rear_c = np.array([0.0, rk[:, 1].max() - 0.04, rk[:, 2].min() + 0.006])
    RACK_TUBES = [("goosefit_rack_post", np.array([0.0, clampS2[1], clampS2[2]]), rack_front, 1.0)]
    for sx, tag in ((1, "L"), (-1, "R")):
        RACK_TUBES.append((f"goosefit_rack_stay_{tag}", np.array([sx * RACK_STAY_X, hubR2[1], hubR2[2]]),
                           np.array([sx * RACK_STAY_X, rack_rear_c[1], rack_rear_c[2]]), 0.6))
    clearance = {n: round(float(tyre_dist(_v(n)).min()), 4) for n in allnames if n not in groups["Wheel_R"]}
    rear_inside = {n: c for n, c in clearance.items() if c < 0}

    # gooseneck stub off the captain post (the stoker bars now stand on the top tube)
    fr = _o("Cylinder")
    bm = bmesh.new()
    bm.from_mesh(fr.data)
    ov = old["Cylinder"]
    y0, y1 = GOOSENECK["y"]
    kill = [f for f in bm.faces if all(y0 < ov[v.index][1] < y1 and ov[v.index][2] > GOOSENECK["z_min"] for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(fr.data)
    bm.free()

    # new tubes: frame paint (UV of a frame vertex on the boom underside), the shared material
    me = fr.data
    fv = np.array([v.co[:] for v in me.vertices])
    target = (bbF2 + bbR2) / 2 - np.array([0, 0, 0.012 * k])
    vi = int(np.argmin(np.linalg.norm(fv - target, axis=1)))
    uv = next(me.uv_layers[0].data[li].uv.copy() for p in me.polygons for li in p.loop_indices
              if me.loops[li].vertex_index == vi)
    mat = me.materials[0]
    r = 0.0125 * k
    ring_hi2 = Ff(ring_hi)[0]
    if d_bar > 0.002:
        _tube("goosefit_quill", ring_hi2 - axis * 0.02, ring_hi2 + axis * (d_bar + 0.03), r * 0.9, uv, mat)
    else:
        _tube("goosefit_quill", ring_hi2 - axis * 0.02, ring_hi2 + axis * 0.01, r * 0.9, uv, mat)
    clamp_bar2 = gripS2 + k * (bar_clampS - gripS)
    t = (clamp_bar2[1] - JC2[1]) / (JS2[1] - JC2[1])
    tt = JC2 + (JS2 - JC2) * t
    _tube("goosefit_stoker_stem", np.array([0, clamp_bar2[1], tt[2]]), clamp_bar2 + np.array([0, 0, 0.02]), r, uv, mat)
    _tube("goosefit_stem_ext", stem_top - np.array([0, 0.01 * np.sign(dy), 0]),
          stem_top + np.array([0, dy + 0.01 * np.sign(dy), 0]), r * 0.9, uv, mat)
    for nm, p0, p1, rf in RACK_TUBES:
        _tube(nm, p0, p1, r * rf, uv, mat)
        NEW_TUBES[nm] = "Bike_root"
    for nm, g in NEW_TUBES.items():
        groups[g].append(nm)

    return {"k": round(k, 4), "kc": round(kc, 4), "bar_raise_m": round(float(d_bar), 3), "bar_back_m": round(float(dy), 3),
            "anchors": len(A_old), "gooseneck_faces_cut": len(kill),
            "grip_C_u_error_m": round(float(-(Ff(gripC)[0] + axis * d_bar)[1] - (-gripC2[1])), 3),
            "stoker_stem_m": round(float(clamp_bar2[2] - tt[2]), 3),
            "rear_wheel_inside": rear_inside, "rear_wheel_clearance_m": round(min(clearance.values()), 4),
            "mudguard_push_m": round(mudguard_push, 4), "mudguard_recentre_m": round(mudguard_recentre, 4),
            "rack_bottom_m": round(float(rack_bottom), 3), "rack_len_m": round(float(size[1]), 3)}
