"""Part-to-part warp between a drawn goose (Pete's worn sheets) and OUR mannequin view, driven by body control points.

Per sheet + view, the BODY MODEL is the bare glove figure (only its hands are covered; every panel of a sheet shares
its pose and scale). Control points pair the drawing's anatomy with ours:
  front / rear: head, neck base, torso side edges (waist, hips), each arm tracked down by its gap from the body
                (shoulder -> elbow -> wrist -> hand tip at our rig's proportions), each leg's centre at our hip / knee /
                ankle heights plus the foot, legs' outer edges at mid-thigh and mid-shin;
  side views:   bill tip, head back, front / back body edges at neck, chest, waist, hips, mid-thigh, mid-shin, the toe
                tip and the heel; the arm (it lies over the torso) from our landmarks via the global fit.
The warp is moving-least-squares (affine, Schaefer et al. 2006) from OUR view pixels to the drawing's pixels, on a
4 px grid, bilinear in between, plus the global similarity at the frame corners (keeps far pixels still).
"""
import numpy as np
from PIL import Image

import goose2d as g2

J, T = g2.J, g2.T
CHAIN = [J["LeftArm"], J["LeftForeArm"], J["LeftHand"], T["LeftHand"]]
_SEG = [np.linalg.norm(CHAIN[i + 1] - CHAIN[i]) for i in range(3)]
F_E, F_W = _SEG[0] / sum(_SEG), (_SEG[0] + _SEG[1]) / sum(_SEG)


def body_src(view):
    if view == "rear":
        return g2.WORN / "glove" / "rear_v2_raw.png"
    return g2.WORN / "glove" / f"{view}_raw.png"


def runs_of(row):
    xs = np.where(row)[0]
    if not len(xs):
        return []
    return [(int(q[0]), int(q[-1])) for q in np.split(xs, np.where(np.diff(xs) > 2)[0] + 1)]


def central(row, cx):
    for a, b in runs_of(row):
        if a <= cx <= b:
            return a, b
    return None


def track_arm(m, pv, sd, cx, v_lo):
    """Follow one continuous arm run (outer run on side sd, separated from the body) from the shoulder downward."""
    pts, miss = [], 0
    for r in range(int(pv[1]) + 5, min(v_lo, m.shape[0])):
        xs = np.where(m[r])[0]
        xs = xs[sd * (xs - cx) > 0]
        found = None
        if len(xs) >= 2:
            xs = np.sort(xs) if sd > 0 else np.sort(xs)[::-1]
            gaps = np.where(np.abs(np.diff(xs)) > 2)[0]
            if len(gaps):
                outer = xs[gaps[-1] + 1:]
                if (pts and abs(outer.mean() - pts[-1][0]) < 12) or (not pts and len(outer) >= 8):
                    found = (outer.mean(), r)
        if found:
            pts.append(found)
            miss = 0
        elif pts:
            miss += 1
            if miss > 4:
                if len(pts) < 15:
                    pts, miss = [], 0
                    continue
                break
    return pts


def along(poly, f):
    L = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(poly, axis=0).T))])
    t = f * L[-1]
    i = min(max(np.searchsorted(L, t), 1), len(L) - 1)
    a = (t - L[i - 1]) / max(L[i] - L[i - 1], 1e-9)
    return poly[i - 1] + a * (poly[i] - poly[i - 1])


def control_points(view, dm, ref=None):
    """Pairs (ours view px, drawing px) for the body model figure. dm = its matte, ref = its RGB (dark-snap)."""
    man, mm = g2.mannequin(view)
    iou, s, tx, ty = g2.fit_sim(dm, mm)
    to_d = lambda xy: np.array([(xy[0] - tx) / s, (xy[1] - ty) / s])  # noqa: E731
    P = lambda p: g2.to_px(p, view)[0]  # noqa: E731
    ours, theirs, names = [], [], []

    def pair(name, o, d):
        if d is None or o is None:
            return
        ours.append(np.asarray(o, float))
        theirs.append(np.asarray(d, float))
        names.append(name)

    def row_d(z):                                   # drawing row of our height z (global fit)
        return int(round((g2.z_to_row(z) - ty) / s))

    cx_o = P(np.array([0, 0.02, 1.0]))[0]
    cx_d = to_d((cx_o, 0))[0]
    if view in ("front", "rear"):
        pair("head", P(J["Neck3"] + np.array([0, -0.06, 0.10])), to_d(P(J["Neck3"] + np.array([0, -0.06, 0.10]))))
        pair("neck_base", P(J["Neck"]), to_d(P(J["Neck"])))
        for zname, z in (("waist", J["Spine"][2]), ("hips", J["Hips"][2] + 0.03)):
            ro = int(round(g2.z_to_row(z)))
            rd = row_d(z)
            co = central(mm[ro], int(cx_o))
            cd = central(dm[rd], int(cx_d)) if 0 <= rd < dm.shape[0] else None
            if co and cd and (cd[1] - cd[0]) < 1.4 * (co[1] - co[0]) / s:
                pair(f"{zname}_a", (co[0], ro), (cd[0], rd))
                pair(f"{zname}_b", (co[1], ro), (cd[1], rd))
        for side in ("Left", "Right"):
            pv_o = P(J[f"{side}Arm"])
            tip_o = P(T[f"{side}Hand"])
            sd = 1 if tip_o[0] > cx_o else -1
            pv_d = to_d(pv_o)
            pts = track_arm(dm, pv_d, sd, cx_d, row_d(0.45))
            pair(f"shoulder_{side}", pv_o, pv_d)
            if pts:
                end = np.array(pts[-1], float)
                if ref is not None:                    # the hand: dark pixels just below the track's end
                    lum = ref.mean(-1) / 255
                    dy, dx = np.where(dm & (lum < 0.22))
                    near = (np.abs(dx - end[0]) < 25) & (dy >= end[1] - 10) & (dy < end[1] + 60)
                    if near.any():
                        end = np.array([dx[near][np.argmax(dy[near])], dy[near].max()], float)
                poly = np.array([pv_d] + [np.array(p_, float) for p_ in pts] + [end])
                pair(f"elbow_{side}", P(J[f"{side}ForeArm"]), along(poly, F_E))
                pair(f"wrist_{side}", P(J[f"{side}Hand"]), along(poly, F_W))
                pair(f"hand_{side}", tip_o, end)
            for jn, f in (("UpLeg", 0.0), ("Leg", 0.0), ("Foot", 0.0)):
                p = J[f"{side}{jn}"]
                o = P(p)
                rd = row_d(p[2])
                if jn == "UpLeg":
                    continue                           # the hip joint sits inside the torso: no edge to find
                if 0 <= rd < dm.shape[0]:
                    rr = [q for q in runs_of(dm[rd]) if sd * ((q[0] + q[1]) / 2 - cx_d) > 0]
                    if rr:
                        q = min(rr, key=lambda q: abs((q[0] + q[1]) / 2 - cx_d))
                        pair(f"{jn}_{side}", o, ((q[0] + q[1]) / 2, rd))
            for zname, z in (("thigh", (J[f"{side}UpLeg"][2] + J[f"{side}Leg"][2]) / 2),
                             ("shin", (J[f"{side}Leg"][2] + J[f"{side}Foot"][2]) / 2)):
                ro, rd = int(round(g2.z_to_row(z))), row_d(z)
                ro_runs = [q for q in runs_of(mm[ro]) if sd * ((q[0] + q[1]) / 2 - cx_o) > 0]
                rd_runs = [q for q in runs_of(dm[rd]) if sd * ((q[0] + q[1]) / 2 - cx_d) > 0] if 0 <= rd < dm.shape[0] else []
                if ro_runs and rd_runs:
                    qo = min(ro_runs, key=lambda q: abs((q[0] + q[1]) / 2 - cx_o))
                    qd = min(rd_runs, key=lambda q: abs((q[0] + q[1]) / 2 - cx_d))
                    pair(f"{zname}_out_{side}", (qo[1] if sd > 0 else qo[0], ro), (qd[1] if sd > 0 else qd[0], rd))
                    pair(f"{zname}_in_{side}", (qo[0] if sd > 0 else qo[1], ro), (qd[0] if sd > 0 else qd[1], rd))
        # feet: lowest figure row, per side
        for side in ("Left", "Right"):
            sd = 1 if P(T[f"{side}Hand"])[0] > cx_o else -1
            for m_, lst, cx_ in ((mm, "o", cx_o), (dm, "d", cx_d)):
                ys, xs = np.where(m_)
                sel = sd * (xs - cx_) > 0
                yb = ys[sel].max()
                xb = xs[sel][ys[sel] >= yb - 2].mean()
                if lst == "o":
                    fo = (xb, yb)
                else:
                    fd = (xb, yb)
            pair(f"sole_{side}", fo, fd)
    else:
        fwd = -1 if view == "left" else 1                  # image direction the goose faces
        for zname, z in (("neck", J["Neck1"][2]), ("chest", J["Spine2"][2]), ("waist", J["Spine"][2]),
                         ("hips", J["Hips"][2] + 0.03), ("thigh", 0.55), ("shin", 0.25)):
            ro, rd = int(round(g2.z_to_row(z))), row_d(z)
            if not (0 <= rd < dm.shape[0]):
                continue
            co, cd = central(mm[ro], int(cx_o)), central(dm[rd], int(cx_d))
            if co is None or cd is None:
                ro_r, rd_r = runs_of(mm[ro]), runs_of(dm[rd])
                if not ro_r or not rd_r:
                    continue
                co = min(ro_r, key=lambda q: abs((q[0] + q[1]) / 2 - cx_o))
                cd = min(rd_r, key=lambda q: abs((q[0] + q[1]) / 2 - cx_d))
            pair(f"{zname}_front", ((co[0] if fwd < 0 else co[1]), ro), ((cd[0] if fwd < 0 else cd[1]), rd))
            if zname not in ("hips",):                       # the tail spoils the back edge at the hips
                pair(f"{zname}_back", ((co[1] if fwd < 0 else co[0]), ro), ((cd[1] if fwd < 0 else cd[0]), rd))
        for m_, key in ((mm, "o"), (dm, "d")):            # bill tip: the most forward pixel in the head band
            ys, xs = np.where(m_)
            top = ys.min()
            band = ys < top + (0.12 * g2.PPM if key == "o" else 0.12 * g2.PPM / s)
            i = np.argmin(xs[band] * -fwd)
            if key == "o":
                bo = (xs[band][i], ys[band][i])
            else:
                bd = (xs[band][i], ys[band][i])
        pair("bill", bo, bd)
        for m_, key in ((mm, "o"), (dm, "d")):            # toe tip / heel: the bottom 3% of the figure
            ys, xs = np.where(m_)
            bot = ys > ys.max() - 0.03 * (ys.max() - ys.min())
            if key == "o":
                to_, he_ = (xs[bot][np.argmin(xs[bot] * -fwd)], ys.max()), (xs[bot][np.argmax(xs[bot] * -fwd)], ys.max())
            else:
                td, hd = (xs[bot][np.argmin(xs[bot] * -fwd)], ys.max()), (xs[bot][np.argmax(xs[bot] * -fwd)], ys.max())
        pair("toe", to_, td)
        pair("heel", he_, hd)
        k = "Left" if view == "left" else "Right"
        for jn in ("Arm", "ForeArm", "Hand"):
            pair(f"{jn}_{k}", P(J[f"{k}{jn}"]), to_d(P(J[f"{k}{jn}"])))
    # head top: the topmost figure pixel (the hat sits there), in every view
    ys, xs = np.where(mm)
    yo = ys.min()
    ys2, xs2 = np.where(dm)
    yd = ys2.min()
    pair("head_top", (xs[ys <= yo + 2].mean(), yo), (xs2[ys2 <= yd + 2].mean(), yd))
    # frame corners follow the global fit (keeps far pixels still)
    for x, y in ((0, 0), (g2.W0 - 1, 0), (0, g2.H0 - 1), (g2.W0 - 1, g2.H0 - 1)):
        pair("corner", (x, y), to_d((x, y)))
    return {"ours": np.array(ours), "theirs": np.array(theirs), "names": names, "sim": (s, tx, ty), "iou": iou}


def mls_map(ours, theirs, shape, alpha=1.0, step=4):
    """Affine MLS from OUR view px to drawing px; returns (u, v) float arrays of `shape` (bilinear from a grid)."""
    ys, xs = np.mgrid[0:shape[0] + step:step, 0:shape[1] + step:step]
    V = np.stack([xs.ravel(), ys.ravel()], 1).astype(float)
    p, q = ours, theirs
    d2 = ((V[:, None, :] - p[None]) ** 2).sum(-1)
    w = 1.0 / np.maximum(d2, 1.0) ** alpha
    ws = w.sum(1, keepdims=True)
    ps = (w @ p) / ws
    qs = (w @ q) / ws
    ph = p[None] - ps[:, None]
    qh = q[None] - qs[:, None]
    A = np.einsum("ni,nij,nik->njk", w, ph, ph)          # sum w ph^T ph  (2x2)
    B = np.einsum("ni,nij,nik->njk", w, ph, qh)          # sum w ph^T qh
    M = np.linalg.solve(A + np.eye(2) * 1e-6, B)
    out = np.einsum("nj,njk->nk", V - ps, M) + qs
    gh, gw = ys.shape
    U = out[:, 0].reshape(gh, gw)
    Vv = out[:, 1].reshape(gh, gw)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    fy, fx = yy / step, xx / step
    y0, x0 = np.floor(fy).astype(int), np.floor(fx).astype(int)
    y1, x1 = np.minimum(y0 + 1, gh - 1), np.minimum(x0 + 1, gw - 1)
    ay, ax = fy - y0, fx - x0

    def bil(G):
        return (G[y0, x0] * (1 - ax) * (1 - ay) + G[y0, x1] * ax * (1 - ay) + G[y1, x0] * (1 - ax) * ay +
                G[y1, x1] * ax * ay)
    return bil(U), bil(Vv)


def sample(img, u, v):
    """Nearest-neighbour sample of img at float coords (u, v); out-of-range -> zeros, plus validity mask."""
    ui, vi = np.round(u).astype(int), np.round(v).astype(int)
    ok = (ui >= 0) & (ui < img.shape[1]) & (vi >= 0) & (vi < img.shape[0])
    out = np.zeros(u.shape + img.shape[2:], img.dtype)
    out[ok] = img[vi[ok], ui[ok]]
    return out, ok


def body_model(view):
    ref = np.asarray(Image.open(body_src(view)).convert("RGB"))
    dm = g2.matte(ref)
    cp = control_points(view, dm, ref)
    u, v = mls_map(cp["ours"], cp["theirs"], (g2.H0, g2.W0))
    return {"ref": ref, "matte": dm, "cp": cp, "u": u, "v": v}
