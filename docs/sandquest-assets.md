# SandQuest toy assets: Sir Winston, Lady Victoria and the pedalo (2026-10-21)

Small, game-ready figurines of the two Victorian geese and a tin-toy tandem pedal boat for SandQuest (WebXR sand
table on Quest; the geese are ~8 cm figurines on the sandbox rim, the pedalo rides the river the player digs).

| File | What | Tris | Size | Draw calls | Clips |
|---|---|---|---|---|---|
| `out/sandquest/winston.glb` | Sir Winston (Victorian gent, from `goose_captain_fancy`), skinned, 53 bones | 7,734 | 566 KB | 2 (atlas body + alpha-mask hat feather) | 18 |
| `out/sandquest/victoria.glb` | Lady Victoria (Victorian lady, from `goose_stoker_victorian`), skinned, 53 bones | 7,692 | 543 KB | 2 | 18 |
| `out/sandquest/pedalo.glb` | tin tandem pedalo (procedural, vertex-painted) | 1,570 | 71 KB | 9 (hull/wheel/2 cranks/flag x paint+brass) | 1 (`Paddle`) |

Copies of the three GLBs are in `C:\Users\pete\SoftwareDev\sandquest-puzzle\public\gltf\` (`winston.glb`,
`victoria.glb`, `pedalo.glb`). Metadata next to them in `out/sandquest/`: `winston_clips.json`,
`victoria_clips.json`, `pedalo_info.json`; the baked atlases `winston_atlas.png` / `victoria_atlas.png` (1024, for
review; the GLBs carry 512 px JPEG q80). Review renders: `renders/sandquest/pedalo_sheet.png` (both geese seated,
pedalling, 4 views, Eevee), `renders/sandquest/{winston,victoria}_check.png` + `_poses.png` (three.js r161, every
clip), `renders/sandquest/pedalo_threejs.png`.

Budgets asked: goose <= 8,000 tris / 700 KB, pedalo <= 3,000 tris / 200 KB, textures <= 512 px. All met. Khronos
glTF validator: 0 errors / 0 warnings on all three (`pedalo.glb` has two "empty node" infos: the seat sockets).

## Conventions the game needs

- **Units** metres, real-world size (Winston 1.94 m tall with hat, Victoria 1.80 m, pedalo 2.44 x 1.12 m); the game
  scales the figurines down (8 cm goose = scale 0.041).
- **Axes** glTF/three.js: +Y up, **+Z forward** (the goose faces +Z; the pedalo's bow is +Z). Feet on y = 0 for the
  geese; the pedalo origin is the waterline centre (y = 0 = waterline, deck top at y = 0.17, draft 0.18).
- **Rig** the standard goose rig, Mixamo-style names (`Hips` root, `Spine..Head`, `Left/Right UpLeg/Leg/Foot/ToeBase`,
  arms, `Neck..Neck3`, `Jaw`, `Tongue`, `LeftEye/RightEye`, `Left/RightEyelidUpper/Lower`, `HatSocket`, `Tail`,
  `Cloth_coat_*` / `Cloth_skirt_*` chains). Same bone names and rest pose as the delivery riders, so anything that
  drives those (Tandemonium's rider code, the Goose Studio clips) works unchanged. Skinned mesh nodes sit at the
  scene root (their own transform is ignored by glTF; move the armature's parent / the `gltf.scene`).
- **Root motion bone** `Hips`. Walk clips move `Hips.position` forward (+Z) for real, feet planted; see "Clips".
- **Materials** one `goose_toy` material (baked 512 px colour atlas, roughness 0.7, no normal/ORM maps: at toy
  scale they do not read) + `goose_feather` (alpha MASK card, 64x128 PNG). Pedalo: `pedalo_paint` (COLOR_0 vertex
  colours; three.js applies them automatically) + `pedalo_brass` (metallic 1, roughness 0.3).
- **Extensions** `KHR_mesh_quantization` (required): normals are normalized BYTE, UVs normalized UNSIGNED_SHORT,
  weights normalized UNSIGNED_BYTE, rotations in clips normalized SHORT. three.js (r1xx+, super-three 0.181 in
  SandQuest) handles all of it in `GLTFLoader` with no plugin.

## Clips (per goose; durations in seconds)

| Clip | Dur | Loop | Bones it drives | Notes |
|---|---|---|---|---|
| `idle` | 2.00 | yes | Spine1/2, Neck2, Head, Left/RightArm | breathing + sway |
| `blink` | 0.50 | no | 4 eyelid bones | play on top of anything |
| `look_around` | 3.00 | no | Neck3, Head, both eyes | |
| `honk` | 1.25 | no | Neck, Neck1, Head, Jaw, Tongue | jaw opens ~30 deg, tongue out |
| `Pedal_Captain` / `Pedal_Stoker` | 1.00 | yes | Hips, legs, cloth chains **and** the seated upper body | one crank turn; the upper body (hands on the boat's bar / rail) is the delivery `Ride_<seat>` pose baked in, so it is a complete riding clip on its own |
| `idle_shift` | 4.00 | yes | whole body | weight shifts |
| `walk_start` | 0.54 | no | whole body | root_dist 0.144 m; footfall Right @0.45 s |
| `walk` | 0.92 | yes | whole body | root_speed 0.533 m/s (0.48 m per loop); footfalls Left @0.36, Right @0.81 |
| `walk_stop` | 0.75 | no | whole body | root_dist 0.096 m; footfall Left @0.40 |
| `turn_L90` / `turn_R90` | 1.00 | no | whole body | yaw_end +90 / -90 deg (left = +Y rotation) |
| `hat_tip` | 1.92 | no | upper body (+HatSocket) | gent's gesture (also baked on the lady) |
| `curtsy` | 2.21 | no | whole body | |
| `bow` | 2.00 | no | upper body | |
| `wave` | 2.08 | no | right arm, head | |
| `admire` | 2.50 | no | upper body | looks down at itself |
| `celebrate` | 1.50 | no | whole body | hop |
| `flap_startle` | 1.00 | no | arms, neck | |

Dropped on purpose: `pose_*` (one-frame poses), `Ride_*` (baked into `Pedal_*`), `Lean_*` (no bike to lean),
`twirl` (not on the keep list; 23 KB, easy to add back: `KEEP_BODY` in `scripts/sandquest_goose.py`).

**Layering.** Every clip carries only the bones it actually moves (channels that stay at the rest pose are
removed, `scripts/glb_toy_pack.py`). three.js restores the rest pose for bones no running action touches, so you
can run `blink` / `look_around` / `honk` on top of `walk` or `Pedal_*` with plain `mixer.clipAction(...).play()` and
no track filtering: the face clips own the face bones, the body clips never key them (Goose Studio rule). The one
overlap: `idle` and `Pedal_*` both key the spine/neck/arms; cross-fade between them rather than stacking, or give
`idle` a small weight for breathing while pedalling.

**Root motion.** `walk_start` / `walk` / `walk_stop` move `Hips.position.z` forward inside the clip (object space,
feet planted). Either (a) strip the `Hips.position` track and move the goose by `root_speed * dt` (walk) /
`root_dist` over the clip (start/stop), or (b) keep the track and, when the clip ends, snap the object forward by
`root_dist` (walk: 0.48 m per loop) and reset. `turn_*` rotate the Hips about the origin; at the end, rotate the
object by `yaw_end` and continue with `idle`/`idle_shift`. All numbers are in `<goose>_clips.json` (`root_speed`,
`root_dist`, `yaw_end`, `footfalls` for step sounds, `hip_mid_rest`, `hips_rest`).

**Clip metadata JSON** (`out/sandquest/winston_clips.json`, `victoria_clips.json`): `clips.<name>.{duration, loop,
layer (face|body|ride), root_speed, root_dist, yaw_end, footfalls}`, plus `hip_mid_rest` (mid-point of the hip
joints in rest, metres, +Y up), `ride_grip` (where each hand is in the Ride pose, rig space: the pedalo's bar and
rail are built there), `pedal_feet_frame0`.

## Water-cycle (the game's `pedalo.glb` since 2026-10-22)

Pete swapped the tin pedalo for a period **water-cycle** after a reference photo: a black tandem bicycle frame
raised on diagonal struts over two long, narrow, pointed floats (varnished, cream deck strip, red waterline), the
paddle wheel at the stern where the rear wheel would be (chain from the stoker's crank), upright brass bars for the
captain, the stoker's bars on the captain's seat post, sprung leather saddles. `scripts/make_watercycle.py`; 2,080
tris, 95 KB packed, 3.04 x 1.15 m (bow 1.62 m ahead of the origin, stern 1.42 m behind).

**Same contract as the tin pedalo below** (node names, `Paddle` clip, crank phase, socket use), so the game only
changed its pick-up length. What moved: the riders sit higher, `Seat_Captain` (0, 0.40, 0.36), `Seat_Stoker`
(0, 0.40, -0.282); the paddle wheel is at (0, 0.15, -1.32), radius 0.30. No `Flag` node. Numbers in
`out/sandquest/watercycle_info.json`.

```
blender -b --factory-startup --python scripts/make_watercycle.py -- --sheet     # out/sandquest/watercycle_raw.glb + renders/sandquest/watercycle_sheet.png
/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe scripts/glb_toy_pack.py out/sandquest/watercycle_raw.glb out/sandquest/watercycle.glb --keep-colors
cp out/sandquest/watercycle.glb ../sandquest-puzzle/public/gltf/pedalo.glb
```

## Pedalo (the original tin pedal boat, kept for reference)

Procedural tin toy (`scripts/make_pedalo.py`): two pontoons (cream top, red belt at the waterline, teal below),
tin deck plate with teal trim, a narrow central spine that houses the cranks, two pedestal bench seats in line
(captain front, stoker behind: the same 0.642 m seat spacing as the goose tandem), a brass steering T for the
captain and a brass grab rail (on the back of the captain's seat) for the stoker, an 8-paddle wheel between the
hulls at the stern, a brass pole with a red pennant.

Nodes (positions in `pedalo_info.json`, metres, +Y up, +Z forward, origin = waterline centre):

| Node | Position (x, y, z) | Use |
|---|---|---|
| `Seat_Captain` | (0, 0.19, 0.300) | **put the goose rig origin here** (identity rotation). The 0.11 m hip-above-saddle offset used by the game's tandem is already baked in, so `socket.add(winstonScene)` with no offset seats him. |
| `Seat_Stoker` | (0, 0.19, -0.342) | same for Victoria |
| `Crank_F` | (0, 0.376, 0.468) | front crank (captain); rotates about local +X |
| `Crank_R` | (0, 0.377, -0.175) | rear crank (stoker) |
| `PaddleWheel` | (0, 0.12, -0.812) | radius 0.27, dips 0.15 below the waterline; rotates about local +X |
| `Flag` | (0, 1.05, -1.00) | pennant, origin at the pole top; flutter it if you like |

The seat sockets are 0.19 above the waterline (2 cm over the deck): the feet never touch the deck at the bottom of
the stroke. Saddle tops are at y = 0.89 (`saddle_top` in the JSON) if you want to place something else.

**Clip `Paddle`** (1.0 s, loop): one full turn about local +X on `PaddleWheel`, `Crank_F` and `Crank_R` together,
positive rotation = top of the wheel moves forward (pushes water aft). Its phase matches the geese: at t = 0 the
left pedal is at the top and so is the left foot in `Pedal_*` frame 0. So drive both from the same crank angle:
`t = (crankAngle / 2pi) mod 1`, `paddleAction.time = t`, `pedalAction.time = t` (set `timeScale = 0`, or play both at
the same `timeScale`). The wheel is direct-drive (one wheel turn per crank turn); if the boat should move at speed
`v` with a wheel of radius 0.27, a turn covers roughly `2 * pi * 0.27 * 0.6 = 1.0 m` of water (paddles slip), i.e.
crank rate ~ `v / 1.0` turns per second looks right. The deck and seats are rigid: nothing else animates.

## How it was built

```
# goose: import delivery GLB + Studio clips GLB, decimate, bake atlas, merge clips, export
blender -b --factory-startup --python scripts/sandquest_goose.py -- --goose winston     # out/sandquest/winston_raw.glb + winston_clips.json
blender -b --factory-startup --python scripts/sandquest_goose.py -- --goose victoria
# pack: animations + vertex attributes (new, scripts/glb_toy_pack.py), then images (existing glb_pack_images.py)
.venv/python scripts/glb_toy_pack.py out/sandquest/winston_raw.glb out/sandquest/winston_packed.glb
.venv/python scripts/glb_pack_images.py out/sandquest/winston_packed.glb out/sandquest/winston.glb --max 512 --quality 80
# pedalo (+ review sheet with both toy geese seated)
blender -b --factory-startup --python scripts/make_pedalo.py -- --sheet                 # out/sandquest/pedalo_raw.glb, pedalo_info.json, renders/sandquest/pedalo_sheet.png
.venv/python scripts/glb_toy_pack.py out/sandquest/pedalo_raw.glb out/sandquest/pedalo.glb --keep-colors
# checks
node tools/threejs_check/check.mjs out/sandquest/winston.glb renders/sandquest/winston_check.png
node tools/threejs_check/prop_check.mjs out/sandquest/pedalo.glb renders/sandquest/pedalo_threejs.png 0,40,90,200
node -e "require(process.env.TEMP+'/gv/node_modules/gltf-validator').validateBytes(new Uint8Array(require('fs').readFileSync('out/sandquest/winston.glb'))).then(r=>console.log(r.issues))"
```

`scripts/sandquest_goose.py` (Blender 5.2), per goose:
1. Imports `out/delivery/<goose>.glb`; drops the layered `__` sub-meshes (everything is worn), the stray
   `Icosphere` that is in both delivery files (an 80-tri unit sphere at the origin, no material: worth removing from
   the delivery too), and the coat lining + piping materials (16.5k tris of 0.3 mm trim).
2. Converts the bone-parented eye parts (eyeballs, lids, catchlights) to skinned geometry (one vertex group each)
   so the whole goose is one mesh, welds the garment builders' split vertices (`remove_doubles`, without which the
   decimator cannot collapse across them and the result was 2.7x the vertices), splits by material and decimates
   each piece (Decimate collapse, vertex groups kept) to a per-piece target solved from the 8k budget: head 0.6,
   eyes/lids 0.3, feather 0.15, brass details floored at 60 tris, cloth shares the rest by area^0.6.
3. Joins everything, smart-UV-projects the textured faces into the left 79 % of one atlas; every solid-colour
   material gets a flat patch in the right-hand strip (no UV seams on brass/boots/lids, patches big enough for
   mipmaps). Bakes every material's base colour with Cycles (colour pass only) into a 1024 atlas, then one
   material. The hat feather stays a separate alpha-masked piece (second draw call).
4. Imports `out/show/<goose>_clips.glb` (armature only, identical rest pose, checked bone by bone), re-targets its
   actions onto the delivery rig by bone name (NLA tracks + action slots, Blender 5.2), composes `Pedal_<seat>`
   with the `Ride_<seat>` upper body (frames 1..24 + frame 1 again for a seamless 1.0 s loop), keeps the face clips,
   drops `pose_*`/`Ride_*`/`Lean_*`/`twirl`. **Merged-clip approach worked**; no second clips file is needed.
5. Exports +Y up with every NLA track as a glTF animation (`export_optimize_animation_size`, slide to zero).

`scripts/glb_toy_pack.py` (new, PIL/numpy venv): drops animation channels that never leave the rest pose, drops
unit scale channels, thins keys (Douglas-Peucker, 0.002 per quaternion component / 1 mm), stores rotations as
normalized SHORT, quantizes mesh attributes (normals BYTE, UVs USHORT, weights UBYTE re-summed to 1, joints with
zero weight set to 0), moves skinned mesh nodes to the scene root, rebuilds the binary tightly. Goose animations
went from 297 KB (18 clips, every bone sampled) to ~60 KB. `--keep-colors` keeps COLOR_0 (pedalo).

## Numbers

| | Winston | Victoria | Pedalo |
|---|---|---|---|
| tris / verts (glTF) | 7,734 / 9,520 | 7,692 / 8,509 | 1,570 / 2,694 |
| geometry | 297 KB | 270 KB | 57 KB |
| animations (18 / 18 / 1 clips) | 58 KB | 66 KB | 1 KB |
| images | 64 KB (512 atlas JPEG + 64x128 feather PNG) | 47 KB | 0 |
| JSON | 141 KB | 157 KB | 9 KB |
| total | 566 KB | 543 KB | 71 KB |

The JSON is big because 18 clips x ~32 channels each carry their own accessor entries; gzip on the server takes it
to ~25 KB. If it matters, drop clips (each is 3-8 KB JSON) or quantize key times to shared per-clip inputs.

## What I would improve next

- **Vertex count**: the UV atlas seams double the glTF vertex count (4.5k mesh verts -> 9.5k). A hand-made UV
  layout (or `--uv orig` once the garments' own islands are tidier) would halve the geometry. Not needed for the
  budget.
- **Decimated silhouette**: the coat buttons and cuff rims are 60-tri blobs; the feather card is a 150-tri sliver.
  At 8 cm nothing of this reads, but a close-up VR grab would show faceting on the hat brim and boots.
- **Atlas**: the bake is colour only; brass/piping lose their metallic look (they are yellow paint now). A second
  tiny roughness/metallic bake would bring the sparkle back for ~20 KB.
- **Pedalo**: no steering animation, no rider-specific foot rests (the Pedal clips' feet orbit the crank, the
  pedal pegs are at the orbit radius 0.162 m). The wheel has no housing; the deck stops short of it.
- **Delivery GLBs** carry a stray `Icosphere` (80 tris, unit sphere, no material, unparented) -- remove it upstream.
