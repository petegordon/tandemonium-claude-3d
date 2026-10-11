# Goose-fit tandem: measurements and frame geometry (step 1, for review)

Status 2026-10-11: proposal at gate. Nothing in the bike meshes has changed yet.

Why: P4.2 showed the game's tandem (a human bike) can't fit the geese at any one scale.
- **A (k=0.63):** the geese look too big for the bike.
- **B/C (k=0.8):** the legs need stretching and the bars have to come up 35 cm.

Pete's direction:
1. Geometry first.
2. Build a tandem to the geese's measurements, from the existing bike's parts.
3. Apply styling afterwards. Styling may change the look, but not the contact points: saddles, bottom brackets, pedals and grips.

Scripts:
- `scripts/measure_geese.py` (Blender) writes `out/fit/geese_measure.json`.
- `scripts/frame_fit.py` (helper Python) writes `out/fit/frame_fit.json` and `docs/img/fit_frame_side.png`.

## 1. Rider measurements (rest pose, metres)

| | male (captain) | female (stoker) |
|---|---|---|
| standing height to the head (sole to crown) | 1.65 | 1.75 |
| with the hat | 1.70 | 1.86 (tall hat) |
| hip joint height above the sole (≈ inseam) | 0.72 | 0.81 |
| thigh + shin | 0.351 + 0.250 = **0.60** | 0.404 + 0.287 = **0.69** |
| hip to shoulder (torso) | 0.50 | 0.50 |
| upper arm + forearm (hand) | 0.257 + 0.257 (0.187) | same |
| shoulder width: joints / mesh | 0.21 / 0.51 | 0.19 / 0.46 |
| legwear width at the seat (breeches / skirt) | 0.41 | 0.47 |
| boot length | 0.29 | 0.27 |
| skirt hem: height / width / depth | — | 0.23 / 0.62 / 0.63 |

Notes:
- The two geese share the same torso and arms. The female's legs are 15% longer: her body sliders lengthened them.
- The female's soles sit 9.6 cm below the rig origin in `outfit_female_dressed`. Standing on the ground, her feet would sink. This doesn't matter for riding, but it needs a fix before she ever walks.

## 2. Frame rules (`frame_fit.py`)

Rules applied to each rider:
- **Crank length:** 20% of inseam, a common human rule. One length for both riders, because a tandem shares the timing chain.
- **Bottom bracket height:** crank length + 10 cm, so the bottom pedal clears the ground at the game's bike tilt.
- **Seat tube angle:** knee over the pedal spindle at 3 o'clock (KOPS), clamped to 66–76°.
- **Saddle height:** on the seat-tube line, with the hip-to-ankle distance at 95% of leg length at the farthest point of the stroke. This is the same contact model as `ride_fit.py`: ball of the foot on the pedal, toes 12° down, hip joint 11 cm above the saddle top.
- **Upper body and grips:**
  - torso lean 15° for the captain, 10° for the stoker;
  - wrist at 90% of arm reach, 35° below horizontal;
  - handshake grip under the hand.
- **Front wheel:** placed so the toe clears the tyre at 3 o'clock. Steer axis at 70° with a 45 mm fork offset.
- **Stoker position:**
  - her grips sit 22 cm behind the captain's hip joint, clear of the saddle, breeches and coat;
  - her bottom bracket goes wherever her reach puts it;
  - her knee must stay at least 4 cm from the captain's back.
- **Chainstay:** rear tyre 8 cm behind the stoker's bottom bracket.

## 3. Results (24 in wheels; compared with the current bike at true size)

| | current bike (true size) | **fit, male legs as built** | **fit, male legs ×1.15** |
|---|---|---|---|
| wheel | 28 in (71 cm) | 24 in (61 cm) | 24 in |
| crank | 158 mm | 143 mm | 161 mm |
| bottom bracket height | 31 cm | 24 cm | 26 cm |
| wheelbase / length | 2.00 / 2.72 m | 1.64 / 2.25 m | 1.70 / 2.31 m |
| bottom-bracket spacing | 0.72 m | 0.65 m | 0.68 m |
| captain saddle / grips | 1.09 / 1.06 m | 0.70 / 0.93 m | 0.78 / 1.01 m |
| captain seat angle / hip angle at the top of the stroke | — | 71° / 104° | 70° / 102° |
| stoker saddle / grips | 1.09 / 1.06 m | 0.78 / 1.02 m | 0.78 / 1.02 m |
| stoker knee to the captain's back | — | 16 cm | 15 cm |

Readings:
- Both fits seat the geese **without stretching and without raised bars**. The legs reach at 95%, the hips stay open (over 100° at the top of the stroke), and the knees sit over the pedals.
- **Male legs ×1.15** (0.69 m, the same as the female's; C was the closest preview) puts both saddles at 0.78 m and both riders in the same posture. He would stand about 9 cm taller.
- **Stoker bars:** the geese sit upright with long torsos, so the stoker's hands land about 1.0 m up. That's well above the captain's saddle, so they can't use ordinary stoker bars clamped to the captain's seat post. The fit puts them on a **stoker stem rising from the top tube**.
- **Skirt:** the hem is 62 cm wide, so a step-through (drop) rear frame, as on period ladies' tandems, would clear it. That is a styling-stage choice.

## 4. Decisions for Pete

1. **Male leg length:** as built (0.60 m) or ×1.15 (0.69 m, matching the female). Recommended: ×1.15.
2. **Wheel size** (style only; the fit doesn't depend on it): 24 in as drawn, or 26 in (bottom-bracket drop +2.5 cm, bike about 10 cm longer).
3. **Stoker bars:** a stem from the top tube (as drawn), or ordinary bars on the captain's seat post with the stoker leaning well forward.

## 5. Next, once the decisions above are made

1. **Rebuild the frame from the existing 66 meshes, keeping every name** (D13: presets and `bike-model.js`):
   - wheels, saddles, lamp, rack and chainrings scaled whole;
   - tubes, stays, stem, bars and posts re-ended to the new points;
   - cranks shortened.
2. Re-run `make_bike.py`'s rig, sockets, clips and checks on the result.
3. Seat both geese with `ride_fit.py`: no stretch, no bar raise. Then renders, plus a ride in the harness.
4. Styling pass after that.

## 6. Built (2026-10-11, Pete took every recommendation; 24 and 26 in both built to compare)

**Male legs ×1.15**, a permanent change made through the existing body sliders:
- `chars/outfit_male.json` now has `"body_shape": "sliders"`, `"shape": {"leg_length": 1.15}` and `"shells_on_base": true`.
- In `dress_goose.py` step 3b, his clothes (built on the base body) are masked and skinned on the base. The slider shape is then applied to the finished rig and every skinned mesh.
- **Floor fix, both geese:** after shaping, the whole character is lifted so the soles sit on z = 0 (male +9.2 cm, female +9.6 cm).
- **Result:** both geese have 0.69 m legs and hips at 0.81 m, and stand 1.74 m to the head.
- **Poses checked:** rest, T, A, riding, neck and honk, in Blender (`renders/outfit_*_dressed_poses.png`) and in the game's three.js (`renders/outfit_*_goosefit_threejs_poses.png`), all `ok`.
- Released P3 outputs are backed up in `out/_p3_backup/`.
- **Caution:** if any male piece is rebuilt now, its builder sees the slider body. Remove that piece from the base-built set first, or it gets the leg shape twice.

**Arm model fix in `frame_fit.py`:** the lean now bends through the three spine joints as the rig does, and the reach accounts for the sideways step from shoulder to grip. The captain's grips come out 6.5 cm (24 in) or 10 cm (26 in) behind the steer axis.

**Bike:** `make_bike.py --fit out/fit/frame_goosefit_<24|26>in.json --tag goosefit<24|26>` runs `goosefit_bike.py` before the pivots are measured.
- **Rigid groups** (similarity transforms): front end, rear wheel, saddles, cranks (162 mm), pedals and the stoker bars.
- **Captain bars:** slid up the steer axis, then back to the fitted grip.
- **Frame, top tube, stays and rack:** smooth warp anchored every 4 cm along each old and new tube centreline. The seat tubes run to their measured tops, and the down tube goes through its crossing with the captain's seat tube.
- **Kept:** all 66 names.
- **Added:** `goosefit_quill`, `goosefit_stem_ext` and `goosefit_stoker_stem`.
- **Removed:** the gooseneck stub on the captain's post.
- **Results:**
  - 24 in: 27.3k tris, 2.28 m long.
  - 26 in: 27.6k tris, 2.38 m long.
  - `bike_check.mjs`: `ok` for both (names, all presets, clips).

**Seated** with `ride_fit.py --bike goosefit<n> --max-bar-raise 0`, the stoker added to the captain's scene with `--base`:
- no stretch, no bar raise;
- feet and hands exactly on the contacts;
- legs reach 0.94–0.95, arms 0.90–0.91.

Sheet: `docs/img/goosefit_24_26.png`.

Harness: `?bike=goosefit24|goosefit26|p41` (default goosefit24, k = 1). Both geese load by default, and the hip height is read from each goose's skeleton.

Open items:
- **Pete:** choose 24 or 26 in.
- **P5.4:** check her skirt and bustle over the rear wheel and through the pedal stroke. In the generic riding pose her boots come out of the skirt.
- The stoker stem is about 0.4 m tall (styling pass).
- The seat probe can't measure the female (dress); it reports NaN.

## 7. P5.1–P5.4 riding clips (2026-10-11)

**D22 (Pete):** either wheel size is fine, so we use **26 in** (`bike_rigged_goosefit26.glb`; closer to the assembly sheet).

**How the clips are made:** `ride_fit.py --clips` bakes them with the same IK contact model as the fit and exports `out/<char>-goose/<char>_rider.glb`. That file holds the dressed goose, its old clips (idle, blink, honk and the poses) and these:

| clip | length | drives | content |
|---|---|---|---|
| `Pedal_<seat>` | 25 keys, 1.0 s | legs, feet, cloth chains | one crank turn, time = crank angle / 2π (same convention as the bike's `Pedal` clip; the stoker's half turn is in the bike's geometry, D15) |
| `Ride_<seat>` | static | upper body | seated, hands on the grips (handshake grip), head level |
| `Lean_L_<seat>` / `Lean_R_<seat>` | static | upper body | torso rolled 20° (a third each on Spine / Spine1 / Spine2, neck gives back 35%), head level, hands re-gripped |

- **Contacts:** feet and hands are 0 mm off the pedals and grips in every frame.
- **Exporter quirk:** the glTF exporter samples every bone into every clip, so players filter each clip to its bones:
  - Pedal: `(Left|Right)(UpLeg|Leg|Foot|ToeBase)` plus `Cloth_*`;
  - Ride / Lean: Spine…Head and shoulders, arms, hands.
- **Weights:** Ride = 1 − |lean|; Lean_L = max(0, −lean); Lean_R = max(0, lean). The harness does this (`?bike=goosefit26` is now the default, loading `*_rider.glb`).

**Checks:**
- **three.js harness:** `tools/ride_harness/shots.mjs` takes a crank cycle and lean shots with no errors.
- **Blender sheets:** `scripts/p5_sheet.py` writes `docs/img/p5_pedal_cycle.png` (left and right side, 8 crank angles) and `docs/img/p5_lean.png`.

**Open (P5.4 skirt):**
- The bustle skirt is long (hem 23 cm above the soles, 62 cm wide). Seated, it drapes over the rear wheel and down the frame and hides her legs; only the boots show below the hem. It follows the thighs (D12 chains), so nothing tears, but it overlaps the rear wheel.
- **Options:**
  - (a) a riding hem: shorten or lift the skirt only while riding (chain bones raised in `Ride_Stoker`);
  - (b) a step-through rear frame (period ladies' tandem; styling stage);
  - (c) a skirt guard over the rear wheel;
  - (d) accept it.

**P5.4 skirt, option A done (Pete):** `--riding-hem 0.70,0.82,0.92`.
- **How:** while riding, each skirt chain root is scaled toward the waist by sector (back / side / front). The scale is keyed in `Pedal_Stoker` with the chains, so players must apply its scale tracks too; the harness does.
- **Effect:** skirt vertices inside the rear wheel's disc fall from 67 to 21 in every frame. The 21 left are where the bustle sits on the top of the tyre, under the mudguard.
- **Visual:** her boots and lower legs show as she pedals.
- **Off the bike:** unchanged.
- **Option B** (step-through rear frame) is planned for the styling pass. It moves her bar stem.
- **Before/after:** `docs/img/p54_riding_hem.png`.
