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
blender -b --factory-startup --python scripts/make_pf_tandem.py -- --sheet [--crank-r 0.09] [--bar-len 0.37] [--stagger 0] [--wheel-r auto]
```

- Output: `out/pf_tandem/pf_tandem.glb` (~11.4k tris, ~300 KB, 2.13 m long) and `pf_tandem_info.json`. `--sheet` writes
  `renders/pf_tandem/build_sheet.png`, with both geese seated (it needs `out/sandquest/{winston,victoria}{.glb,_clips.json}`).
- Khronos validator: 0 errors, 0 warnings. The 2 infos are the empty seat-socket nodes.
- **Rider fit:** the contact points come from the geese's own Ride numbers (saddle under the hip, the `ride_grip`
  grips) and from the leg reach of their Pedal clip. With hub cranks, the hub height *is* the wheel radius.
- **Picked by Pete 2026-11-06:**
  - crank **9 cm** (option C in `docs/img/pf_tandem/crank_lineup.jpg`): a shorter crank keeps the clip's
    bottom-of-stroke reach, so the hub drops lower and the wheel auto-sizes to just clear the saddle, giving a
    **0.85 m (34 in)** big wheel and a 0.21 m small wheel;
  - cross bar **0.37 m** (`docs/img/pf_tandem/bar_lineup.jpg`), the shortest with the small wheels in line;
    `--stagger` sets them side by side for shorter bars.
- **Pedal clip still needed:** the geese's Pedal clips are built for the game tandem's 0.162 m crank. The sheet poses
  the legs onto the 9 cm pedals with IK, but the game needs a Penny-Farthing pedal clip.
- **Nodes** (glTF: +Y up, +Z forward): `Frame` › `Steer_F` / `Steer_R` (local +Y = steer axis) › `Wheel_F|R` and
  `Crank_F|R`; `Wheel_SF|SR`; `Seat_Captain` (identity rotation) and `Seat_Stoker` (turned 180° about +Y).
- **Clip `Ride`:** one big-wheel turn in 1.0 s, rolling forward. The small wheels turn R/r times faster. The
  rider-left pedal is at the top at t = 0.

## Decided (Pete 2026-11-06)
- The stoker pedals backwards when the bike rolls forward. That's intended.
- Both riders steer and pedal as built. A reverse-lean option for the stoker may come later.

## Open
- Hooking it into the game (the garage, the bike swap, the unlock rule) waits on #611's design questions.
