# P4/P5 plan: the tandem, pedalling and leaning geese

Status: **approved with Pete's answers (2026-10-11, section 3a)**. Nothing in here is built yet. Start the new session from this
file and `RESUME.md`.

## 1. The two candidates

| | A. `tandemonium/tandem-3d/tandem_bicycle.glb` (in the game now) | B. Generate from `refs/v3/bicycle-turnaround.png` (and the assembly PNG) |
|---|---|---|
| What it is | Hand-modelled Sketchfab tandem by Sameer.Rayeen, **CC-BY-4.0**, already credited in the game's `index.html`, `desktop/index.html` and the Steam page. | Image-to-3D (Pixal3D multi-view, as for the geese) from the v3 bicycle sheet. |
| Look vs the reference | Very close to v3: black frame, brass trim, brass headlamp, rear rack, two sprung brown saddles, two handlebars, two cranksets, four pedals. | The reference itself, but the output would be a single fused mesh. |
| Parts | **66 separate named meshes**: wheels (tyre, rim, spokes front and rear), fork, 2 bars, 2 saddles, 4 chainrings / gears, 4 crank arms (`pedal_rod_low*`), 4 pedals (`pedal_low*`), chains, frame tubes, lamp, rack. | One shell. Spokes, chains, cranks and thin tubes are the worst case for image-to-3D; every part would have to be cut out and remodelled. |
| Size | 58.7k tris, one material `cycle` (5 × 1024² textures). | Unknown; would need retopology like the geese. |
| Game hooks | The colour picker presets (`bike-presets*.json`) are keyed by **mesh name**. `js/bike-model.js` finds spokes by name and spins every node whose name contains `pedal` about its own Z from `crankAngle`. The game scales the model to **4.4 m long**. | None. Presets, spoke fade and crank drive would all have to be rebuilt. |
| Risk | Low: the model is known to work in the game. | High: it repeats the garment-shard problems on the thinnest geometry. |

**Recommendation: A.** Keep the game's bike as the 3D asset and keep every mesh name, so the colour picker and
`bike-model.js` keep working. Add a rig and attachment sockets to it.

Use the PNGs as **references, not meshes**:
- **`refs/v2/assembly-turnaround.png`** (the geese on the bike, all-round views) is the target for:
  - fit and posture: where each goose sits, hands on the grips, feet on the pedals;
  - relative size: goose against wheel and saddle height;
  - who sits where: the male captain in front, the female stoker behind.
- **`refs/v3/bicycle-turnaround.png`** is only for checking details: the chain sides, the rear bar mounted on the
  captain's seatpost, the lamp.

## 2. Pipeline (new scripts in tandemonium-claude-3d)

### P4.1 `scripts/make_bike.py`: prepare and rig the bike
1. **Import and units.** Import `tandem_bicycle.glb`. One wheel is 2.18 model units across, which is a 0.71 m
   (28 in) wheel, so 1 unit ≈ 0.326 m and the bike is about 2.7 m long.
2. **Orient.** Convert to metres, forward −Y (the goose convention), ground at z = 0, centred between the axles.
3. **Group parts by name.** Groups: wheel F, wheel R, steer (fork, front bar, lamp), frame (rear bar on the captain's
   seatpost), crank F, crank R (chainring, two arms, chain rod), pedals ×4, chains, saddles.
4. **Measure pivots from the geometry:**
   - hub centres;
   - crank axle centres;
   - pedal spindle centres;
   - steer axis (the fork line).
5. **Armature:**
   - `Bike_root`;
   - `Steer`;
   - `Wheel_F`, `Wheel_R`;
   - `Crank_F`, `Crank_R`;
   - `Pedal_FL`, `Pedal_FR`, `Pedal_RL`, `Pedal_RR` (these counter-rotate so the pedals stay level).

   The meshes are rigid, parented with one bone each, and **mesh names are kept**.
6. **Socket empties** (contact targets for the geese):
   - `Seat_Captain`, `Seat_Stoker`;
   - `Grip_C_L`, `Grip_C_R`, `Grip_S_L`, `Grip_S_R`;
   - `PedalPin_*` (×4).
7. **Clips:** `Pedal` (one crank revolution, looping, with wheels spinning at the gear ratio) and `Steer_L` / `Steer_R`
   poses.
8. **Checks:**
   - glTF validator;
   - three.js check;
   - load a colour preset by name to prove the picker still applies;
   - turntable and crank-cycle renders.

**Gate (Pete):** part grouping, pivots and preset compatibility. Also decide whether to decimate the spokes and tyres:
the bike is 58.7k tris, and the riders it replaces in the game are 500k.

### P4.2 Scale and fit
- The goose defines scale (D1). Seat each goose so that:
  - its hip sits on the saddle;
  - at the bottom of the pedal stroke its foot reaches the pedal with a slight knee bend;
  - its hands reach the grips.
- Cross-check the wheel-to-goose and saddle-to-goose ratios against the assembly sheet.
- Result: one bike scale factor and saddle / bar heights. Saddle posts and bar stems may be raised or lowered, the
  way a real bike is fitted.
- The game later scales the whole group, bike and geese together, to its 4.4 m bike length.

**Gate (Pete):** side and front renders next to the assembly sheet.

### P5.1 Riding pose by contact (male captain first)
- New `scripts/ride_fit.py`. Analytic two-bone IK on the goose rig: Hips → saddle socket, hands → grips, feet → pedal
  pins.
- Spine and neck are tuned so the head is upright and looking ahead, as in the assembly sheet.
- This replaces `rig_poses.Poser.riding` for the bike. The cloth chains (D12) keep the coat tails and skirt
  following the thighs.

### P5.2 Pedalling clip
- Sample one crank revolution (24 frames). The feet stay on the pedal pins and the legs are solved by IK each frame.
- The ankle follows the level pedal.
- The goose clip `Pedal_Captain` / `Pedal_Stoker` is time-mapped to `crankAngle`: the game sets clip time to
  crankAngle / 2π, the same input it already uses to spin the cranks.

### P5.3 Lean
- **Clips:** `Lean_L` / `Lean_R` additive poses (hips, spine and head roll, as Track 1's `CaptainLean` and
  `StokerLean` already do in the game).
- **Contacts:** hands stay on the grips and feet stay on the pedals (IK re-solve baked into the pose).
- **Two lean sources:**
  - each goose leans from its own player's input;
  - the bike tilts from the combined input.

  This is the behaviour already in the game (riders-lean-viz).

### P5.4 Female stoker
- Same as P5.1–P5.3 on the rear sockets and her slider body.
- Extra check: skirt and bustle through the whole pedal stroke. Her knees rise into the skirt, and the chains need
  checking against the frame and the rear wheel.

### P5.5 Delivery
**Recommended: separate GLBs.**
- `bike_rigged.glb` carries the bike rig and sockets.
- Each dressed goose GLB gets the new `Pedal_*` and `Lean_*` clips.
- The game parents each goose root to its seat socket.
- Outfits and colours stay swappable, and versus mode can mix riders.

The alternative is one combined GLB; it's simpler to load but locks the outfits together.

Then game integration on a branch in the tandemonium repo:
- the new bike and the two geese replace `tandem_riders.glb` behind *Show Riders*;
- `crankAngle` drives the bike `Pedal` clip and both geese's pedal clips;
- each player's input drives that goose's lean.

## 3. Questions for Pete

1. **Bike source:** use the game's GLB (A) and keep its mesh names? *(Recommended.)*
2. **Seating:** captain = male in front, stoker = female behind, as in the assembly sheet?
3. **Pedal phase:**
   - Real tandems usually run both cranksets **in phase** (timing chain).
   - The old ROADMAP P5.3 said 180° out of phase.

   Which one?
4. **Steering:** should the front bar and fork turn with steering, with the captain's arms following? Or keep the
   bars fixed? (It's a mechanic, so it's your call.)
5. **Delivery:** separate GLBs with sockets *(recommended)* or one combined GLB?
6. **Triangle budget for the bike:** keep 58.7k, or decimate spokes and tyres toward about 25k?

## 3a. Pete's answers (2026-10-11) — decisions D13–D18

| # | Decision |
|---|---|
| D13 | **Bike source:** the game's `tandem_bicycle.glb`. Keep every mesh name, because the colour presets and `bike-model.js` depend on them. |
| D14 | **Seating:** male captain in front, female stoker behind. |
| D15 | **Pedal phase: 180° out of phase.** Pete has always had the players alternating. This also matches the game: each player's tap is their own leg's push. Captain crank = θ, stoker crank = θ + π. The two chainrings stay linked by the timing chain with a half-turn offset, so it is still a plausible tandem setup. |
| D16 | **Handlebars fixed for now.** First pass is lean and pedalling only. No steering bone animation; a `Steer` pivot is still measured so it can be added later. |
| D17 | **Delivery:** a separate rigged bike GLB with sockets. The geese attach at runtime. |
| D18 | **Bike budget: below 30k tris** (from 58.7k). Decimate the tyres, rims, spokes, chainrings and frame tubes. Keep the silhouette and the mesh names: decimate each mesh in place. |

## 4. Facts for the new session

- **Game code:**
  - `js/config.js`: `BIKE_MODEL_PATH` (riders) and `CHOOSER_MODEL_PATH` (the plain frame).
  - `js/bike-model.js`:
    - scales to 4.4 m;
    - spokes are `cylinder035_cycle_0` / `cylinder024_cycle_0`;
    - every node with `pedal` in its name gets `rotation.z = base + crankDisplay`.
- **Bike GLB metadata:**
  - axes as imported: length on Y, up on Z;
  - bbox −0.61..0.61 × −3.33..5.00 × −1.91..1.44 units.
- **Track 1 rider rig** (`tandem_riders.glb`, fused 500k):
  - bones `Bike_root`, `Bike_Bars`, `Bike_Lamp`, `M_*`, `F_*`;
  - clips `CaptainLean`, `StokerLean`.

  These are the references for lean behaviour.
- **Our geese:** `out/outfit_*-goose/<c>_dressed.glb` (release `p3-dressed-geese`), rig `goose_rig` (Mixamo-style
  names), `scripts/rig_poses.py`.
