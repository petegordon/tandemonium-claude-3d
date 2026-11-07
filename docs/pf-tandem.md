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
blender -b --factory-startup --python scripts/make_pf_tandem.py -- --sheet [--wheel-r 0.36]
```

- Output: `out/pf_tandem/pf_tandem.glb` (~11.4k tris, ~300 KB) and `pf_tandem_info.json`. `--sheet` writes
  `renders/pf_tandem/build_sheet.png`, with both geese seated (it needs `out/sandquest/{winston,victoria}{.glb,_clips.json}`).
- Khronos validator: 0 errors, 0 warnings. The 2 infos are the empty seat-socket nodes.
- **Rider fit:** the contact points come from the geese's own Ride/Pedal numbers (hip over the crank, saddle under
  the hip, the `ride_grip` grips), and the look is scaled to fit them. With hub cranks, the hub height *is* the wheel
  radius, so the legs set the big wheel at 0.72 m (28 in). A bigger, more dramatic wheel means the feet no longer
  reach the pedals.
- **Nodes** (glTF: +Y up, +Z forward): `Frame` › `Steer_F` / `Steer_R` (local +Y = steer axis) › `Wheel_F|R` and
  `Crank_F|R`; `Wheel_SF|SR`; `Seat_Captain` (identity rotation) and `Seat_Stoker` (turned 180° about +Y).
- **Clip `Ride`:** one big-wheel turn in 1.0 s, rolling forward. The small wheels turn R/r times faster. The
  rider-left pedal is at the top at t = 0.

## Open (Pete)
- The stoker faces backwards. When the bike rolls forward her pedals turn backwards for her, so the game would play
  `Pedal_Stoker` reversed. Is that the intended joke, or should the bike roll the stoker's way when she pedals?
- Who steers? Each half has its own bars and fork, and both steer nodes exist.
- Hooking it into the game (the garage, the bike swap, the unlock rule) waits on #611's design questions.
