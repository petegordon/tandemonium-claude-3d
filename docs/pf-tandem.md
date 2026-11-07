# Penny-Farthing tandem (Time Warp bike, Tandemonium #611)

Approved look: `refs/pf_tandem` (2026-11-06). Two penny-farthings back to back, riders facing away from each other,
one straight black-and-gold cross bar with a goose medallion.

## Two passes

### 1. Image-to-3D (look reference)
- `refs/pf_tandem/mesh/{left,front,rear}_raw.png` → `comfy_job.py prep --char pf_tandem/mesh`.
- `scripts/pf_frame_views.py` puts all views on one scale. prep crops each view square to its own mask, so the wide
  side view and the narrow end view came out about 2x apart in scale.
- `comfy_job.py pixal-mv --char pf_tandem/mesh --seed N` was run for seeds 42, 123, 7 and 2026. Outputs are in
  `out/pf_tandem/mesh/`, and `renders/pf_tandem/seeds_compare.png` compares them.
- `scripts/pf_glb_views.py <glb> <png>` renders any GLB full-frame: side, end, 3/4, high 3/4 and top.
- Result: every seed reads as the right bike, but the spokes are broken, the rims wobble, and all the parts are fused
  into one ~495k-triangle shell. Seed 42 is closest to the art. These meshes are kept as reference only.

### 2. Built in code (the game asset)
`scripts/make_pf_tandem.py` follows the same approach as `make_watercycle.py`: vertex colours plus two materials
(`pf_paint`, `pf_gold`).

```
blender -b --factory-startup --python scripts/make_pf_tandem.py -- --sheet [--crank-r 0.09] [--bar-len 0.40] [--stagger 0.045] [--wheel-r auto]
```

- Output: `out/pf_tandem/pf_tandem.glb` (~11.4k tris, ~300 KB, 2.96 m long, 1.26 m / 50 in big wheels) and `pf_tandem_info.json`. `--sheet` writes
  `renders/pf_tandem/build_sheet.png`, with both geese seated (it needs `out/sandquest/{winston,victoria}{.glb,_clips.json}`).
- Khronos validator: 0 errors, 0 warnings. The 2 infos are the empty seat-socket nodes.
- **Rider fit:** the contact points come from the geese's own Ride numbers (saddle under the hip, the `ride_grip`
  grips) and from the leg reach of their Pedal clip. With hub cranks, the hub height *is* the wheel radius.
- **Picked by Pete 2026-11-06:**
  - crank **9 cm** (option C in `docs/img/pf_tandem/crank_lineup.jpg`): a shorter crank keeps the clip's
    bottom-of-stroke reach, so the hub drops lower and the wheel auto-sizes to just clear the saddle, giving a
    **0.85 m (34 in)** big wheel and a 0.21 m small wheel;
  - cross bar **0.40 m** (`docs/img/pf_tandem/bar_lineup.jpg`; 0.37 m is the shortest with the small wheels in line);
    `--stagger` sets them side by side for shorter bars.
- **Leg-reach fix (2026-11-06):** the earlier lineups used 0.52 m from hip to crank, which left out the 11 cm the
  geese's hips sit above the saddle; the correct figure is 0.63 m (goosefit26 as baked). With a 9 cm crank the hub
  sits 0.70 m below the hips, so up to a **1.26 m (50 in)** wheel fits (`--wheel-r auto`). The 34 in pick now
  stands on a taller saddle post. Pete is choosing between them (`docs/img/pf_tandem/pedal_34in.jpg` /
  `pedal_50in.jpg`). The pedal clip is the same for either size.
- **Game contract:** `Seat_*` = where the goose's hips go (game HIP_UP 0); saddle top at the hips. Grips on both
  halves = the game tandem's captain grips relative to his seat (0.167 out, 0.444 ahead, 0.143 up), so each goose's
  existing `Ride_<seat>` / `Lean_*` clips fit either seat.
- **Nodes** (glTF: +Y up, +Z forward): `Frame` › `Steer_F` / `Steer_R` (local +Y = steer axis) › `Wheel_F|R` and
  `Crank_F|R`; `Wheel_SF|SR`; `Seat_Captain` (identity rotation) and `Seat_Stoker` (turned 180° about +Y).
- **Clip `Ride`:** one big-wheel turn in 1.0 s, rolling forward. The small wheels turn R/r times faster. The
  rider-left pedal is at the top at t = 0.

## Pedal clips (`Pedal_PF`)
`bash scripts/bake_pf_clips.sh` writes `out/pf_tandem/clips/<outfit>_pf.glb` (40-90 KB each: armature + one clip,
plus a one-triangle anchor skinned to Hips so it loads as an armature). It runs `ride_fit.py` on
`out/bike/bike_rigged_pf.blend` (written by `make_pf_tandem.py` in the game tandem's bone format) with the new options
`--clip-name Pedal_PF --pedal-only --clip-pack <glb>`.
- One clip per outfit serves both seats: the halves are identical from the rider's seat. The captain plays it
  forwards (time = crank angle / 2pi, rider-left pedal up at 0); the stoker plays it reversed.
- The name matches `/^Pedal_/`, so `goose-rider-clips.js` cuts it to the legs + cloth chains like the tandem clip.
- Results: contact error 0 mm on all 25 frames; bottom-of-stroke leg reach 0.94 (the tandem's is 0.946).
  On the 34 in wheel, skirt vertices inside the tyre plane are 0 for every lady except the fancy lady (6, a centre
  fold). The fancy and Victorian ladies use a tighter riding hem (0.45, 0.6, 0.55) than on the tandem. On the 50 in
  wheel the tyre runs just under the saddle, and long skirts cross it: fancy 53, Victorian ~300, Georgian ~450.
- Preview: `scripts/pf_preview.py <bike> <captain.glb> <captain_pf.glb> <stoker.glb> <stoker_pf.glb> <out_prefix>`
  seats game geese the way `goose-riders.js` does.

| Outfit pack | In-game riders |
|---|---|
| `outfit_male_pf` | goose_captain, goose_stoker_victorian_m |
| `outfit_male_cyclist_pf` | goose_captain_cyclist, goose_stoker_cyclists_m |
| `outfit_male_victorian_pf` | goose_captain_fancy, goose_stoker_fancy_m |
| `outfit_male_georgian_pf` | goose_captain_georgian, goose_stoker_georgian_m |
| `outfit_female_pf` | goose_stoker (fancy lady), goose_captain_fancy_f |
| `outfit_female_cyclist_pf` | goose_stoker_cyclist, goose_captain_cyclists_f |
| `outfit_female_victorian_pf` | goose_stoker_victorian, goose_captain_victorian_f |
| `outfit_female_georgian_pf` | goose_stoker_georgian, goose_captain_georgian_f |

## Decided (Pete 2026-11-06)
- **50 in big wheels** (the most that fits with the 9 cm crank). The 0.40 m bar puts the small wheels side by side
  (`--stagger 0.045`).
- Long skirts meet the tyre just under the saddle. Riding hems for this bike only: fancy and Victorian 0.45/0.6/0.55,
  Georgian 0.25/0.35/0.35 (`docs/img/pf_tandem/georgian_hems_50in.jpg`), cyclist none (her knee-length skirt reads
  fine). The vertex counts overstate what shows at game scale.
- Name: **Time Warp**.
- The stoker pedals backwards when the bike rolls forward. That's intended.
- Both riders steer and pedal as built. A reverse-lean option for the stoker may come later.

## Open
- Hooking it into the game (the garage, the bike swap, the unlock rule) waits on #611's design questions.
