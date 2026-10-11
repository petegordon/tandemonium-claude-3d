# Tandemonium Claude 3D — Male Goose Build Plan

Status (2026-10-10): decisions made (§10). **Male goose v1 DONE (Phases 0–5)** — see follow-ups below; next: Pete review, then female.

### Progress log
- Blender upgraded to **5.2.2 LTS** (winget; 5.1 unregistered, ~1 GB of 5.1 files remain on disk).
- ComfyUI: Desktop is in use by Antigravity on :8000, so Claude uses a **side-by-side
  install** at `C:\Users\pete\ComfyUI-claude` (git v0.39.0, uv venv py3.12, torch
  2.14.1+cu130) on **:8189**, sharing `Documents\ComfyUI\models` via
  `extra_model_paths.yaml`. Start: `.venv\Scripts\python.exe main.py --port 8189
  --extra-model-paths-config extra_model_paths.yaml`.
- Models fetched by `scripts/fetch_models.sh` (native TRELLIS.2 int8, Pixal3D single +
  multi-view int8, DINOv3, TRELLIS.2 VAEs, BiRefNet, MoGe, 4x-UltraSharpV2, Hunyuan3D-2mv).
- Phase 1: `scripts/crop_panels.py` + `comfy_job.py prep` → `refs/male/prepped/`.
- Phase 2 tools: `scripts/comfy_job.py` (pixal-mv / single / hunyuan-mv) and
  `scripts/review_candidate.py` (Blender 5.2 contact sheet + silhouette IoU).

| Candidate | Mean IoU (front/left/back/right) | Peak GPU | Time |
|---|---|---|---|
| Gemini raw TRELLIS (baseline) | 0.788 (.86/.71/.87/.70) | — | — |
| TRELLIS.2 native, front only, 512 | 0.842 (.89/.79/.90/.79) | 10.1 GB | 102 s |
| **Pixal3D multi-view (4 views), 512** | **0.935** (.94/.93/.94/.93) | 10.6 GB | 168 s |
| Hunyuan3D-2mv (4 views), octree 256, shape only | 0.863 (.85/.87/.86/.87) | 9.8 GB | 99 s |
| Pixal3D multi-view, **1024**, 2K tex, seed 42 | 0.937 | 9.3 GB | 198 s |
| Pixal3D multi-view, 1024, seed 7 | 0.935 | 9.0 GB | 201 s |
| Pixal3D multi-view, 1024, seed 123 | 0.941 | 10.0 GB | 213 s |
| Pixal3D multi-view, 1024, seed 2026 | 0.935 | 9.9 GB | 192 s |

1024 tier (run with Antigravity ComfyUI stopped, baseline ~1.7 GB) adds real detail: amber eyes, knotted bow tie,
shirt stud, coat back vent + buttons, sleeve buttons. Silhouette IoU saturates ~0.94, so seed choice is visual
(`renders/closeup_seeds_1024.png`). Candidates: `out/male-goose/candidate_pixalmv_s{42,7,123,2026}_1024.glb`.
**Seed 42 chosen by Pete (2026-10-10).**

- **Phase 3 done** — `scripts/clean_hi.py` → `out/male-goose/male_goose_hi.glb` (496k tris, 1.80 m,
  faces −Y, feet Z=0) + `male_goose.blend` (collection Hi). Welded UV-seam dupes, removed 90
  speck verts, hat recolored olive→reference brown via HSV shift limited to the felt
  (skips black band, cream cheek, eye highlights). Albedo is flat/de-lit already; no de-light pass needed.
- **Phase 4 done** — `scripts/retopo_bake.py` → `out/male-goose/male_goose_game.glb`:
  **19,600 tris**, 1 mesh, 1 material, 1 draw call, 2K BaseColor + Normal + ORM, tangents
  exported, 12.7 MB. Silhouette IoU 0.938 (= hi-poly). Bakes on GPU (OptiX) in ~10 s.
  Retopo = voxel remesh 4 mm → adaptive QEM decimate. **Quadriflow refused/failed** on this
  mesh in Blender 5.2 (passes the manifold check only after decimation, then "Remeshing failed").
- **Phase 5** — Khronos glTF validator: 0 errors / 0 warnings (after
  `scripts/glb_fix_tangents.py`, now run automatically on export: MikkTSpace emitted 4 zero
  tangents on zero-area UV tris). Renders: `renders/game_v1_review.png`, `renders/closeup_hi_vs_game.png`.

**Known follow-ups (male v1):**
1. Topology is triangle-adaptive, not quad edge loops — fine for static/rigid use and light
   skinning; for clean elbow/knee deformation, retopo with Instant Meshes (external binary;
   needs Pete's OK) or a manual quad pass.
2. Small bake smudge on the coat back-left shoulder (ray miss) — fix by cage bake or a texture touch-up.
3. Region vertex groups (hat/coat/waistcoat/…) for future clothing split not yet created.
4. Pete to eyeball in the game's three.js loader (orientation/scale; height still deferred).
### Male goose — fixes needed (v1 → v2), logged 2026-10-10
Evidence renders: `renders/closeup_boots_s42.png` (top = hi 496k, bottom = game 19.6k),
`renders/closeup_hi_vs_game.png`, `renders/game_v1_review.png`.

| # | Issue | Where | Proposed fix |
|---|---|---|---|
| M1 | **Boot toe "wing" flaps** — thin, torn sheet fins sticking sideways out of both toe caps (generator debris on the flat shiny toe surface). Spotted by Pete. | hi + game | In Blender: delete the fins (thin-component / normal-flip select below ankle), rebuild each toe cap (sculpt or a small modeled toe-cap mesh shrinkwrapped to the boot), then re-bake. |
| M2 | **Chrome-like cyan/green reflections on the toes** — boots carry metallic patches, so they mirror the environment. *Confirmed by per-face audit (game ORM): male boots metallic mean 0.067 / **max 0.68** vs rest 0.012; female boots metallic 0.00 with the same roughness (~0.65) and show no chrome — so metallic, not gloss, is the cause.* | texture (metallic/roughness) | `boot_material` plugin (stage hi): in the boot region (z < ~0.25 m) force metallic = 0; leave roughness (~0.65 already reads as polished leather on the female). |
| M3 | **Uneven, squared-off toe shapes** — L/R toes differ; reference has rounded Victorian toes. | hi geometry | After M1, rebuild one boot foot and mirror it (boots are symmetric), keep the button row on the outer side of each. |
| M4 | **Bake smudge** on the back of the coat's left shoulder (ray miss). | game basecolor | Cage bake (cage = game mesh inflated ~5 mm) or a texture touch-up; check after M1 re-bake. |
| M5 | **Topology is adaptive triangles, not quad edge loops** (Quadriflow refuses these meshes in Blender 5.2). | game | For clean elbow/knee/neck skinning: Instant Meshes (external binary — needs Pete's OK) or manual retopo of joints. |
| M6 | **No region vertex groups** (hat/coat/waistcoat/breeches/gloves/boots/head) yet. | game | Classify verts by baked colour + height; needed for M2 masks and the separate-clothing stretch goal. |
| M7 | **Hat colour** is a procedural HSV shift; reads correct but slightly lighter/warmer than "chocolate". | texture | Pete to judge in game; now the `hat_recolor` plugin — tune via `chars/male.json` (e.g. `ref_rgb`). |
| M8 | Not yet viewed in the game's three.js loader (orientation/scale; height deferred). | — | Pete check. |

Generalisation for the female + bike: run a **"shiny dark surfaces" audit** after each
generation (metallic > 0 on non-metal materials, thin fins on flat glossy parts — boots,
hat brims, saddles).
### Fix plugins (design, 2026-10-10)
Per-character corrections are **plugins**, not hard-coded steps, so the same pipeline
runs for male / female / bike and each character opts into the fixes it needs.

```
scripts/fixes/
  __init__.py     registry (auto-discovers modules), run(ctx, specs, stage), parse_cli, load_config
  common.py       FixContext(ob, char, height, root, stats) + helpers: input_image, read/write_pixels,
                  load_ref, rgb_to_hsv/hsv_to_rgb, face_centroids, texel_mask (UV-triangle rasterizer)
  hat_recolor.py  NAME="hat_recolor", STAGE="hi", DEFAULTS={z_frac, hue_deg, sat_min, val, ref_view, ref_rgb}
chars/
  male.json       {"fixes": [{"fix": "hat_recolor", "z_frac": 0.88}], "height_m": 1.8, ...}
  female.json     {"fixes": []}
```
- Plugin contract: `NAME`, `STAGE`, `DEFAULTS` (JSON-able), `apply(ctx, **params) -> dict`.
  Unknown params are rejected; results go into `<char>_goose_hi.json` under `"fixes"`.
- `clean_hi.py` runs every stage-`"hi"` fix from `chars/<char>.json`, plus CLI extras
  `--fix name[:k=v,...]` (repeatable); `--no-config` skips the JSON; `--list-fixes` prints the registry.
- Adding a fix = drop a module in `scripts/fixes/` + list it in a char config. Future stages
  (e.g. `"game"` fixes after retopo) plug into the same `fixes.run(ctx, specs, stage)`.
- Regression-tested: plugin hat_recolor reproduces the male hi textures byte-for-byte.
- **Rule:** `clean_hi.py` rewrites `<char>_goose.blend` from scratch (Hi only) → always re-run
  `retopo_bake.py --stage all` afterwards.

Planned plugins from the male fix list: `boot_material` (M2: metallic→0, leather roughness
in the boot region), `trim_fins` (M1: delete thin sheet fins below the ankle), possibly
`region_groups` (M6, stage "game").




Multi-view is the clear winner (tail, beak length, belly depth, coat vent all correct).
**New vs. the original plan:** ComfyUI's native **Pixal3D multi-view** (TRELLIS.2-based,
takes front/left/back/right) fits a turnaround sheet better than Hunyuan3D-2mv and is
now the primary generator. "Peak GPU" includes ~4.4 GB held by other apps
(Antigravity's ComfyUI, desktop).
Template: the same plan is reused for the **female goose**, then the **tandem bike**
(see §9 for what changes).

Source of truth: `refs/characters-turnaround.png` (top row = male: FRONT, LEFT PROFILE,
REAR, RIDING 3/4). `refs/source-reference.jpg` is the design authority when the sheet
and the original illustration disagree.

---

## 0. Baseline: what Antigravity/Gemini produced

`tandemonium-gemini-3d/male-goose-raw-trellis.glb` (measured from the GLB accessors):

| Metric | Value |
|---|---|
| Meshes / primitives | 1 / 1 |
| **Triangles** | **79,192** |
| Vertices | 62,572 |
| Textures | 2 PNGs (512² per the export settings) |

Why it's capped at ~79k: `submit_trellis.py` ran TRELLIS2 with `resolution=512`,
`max_tokens=24576`, `Trellis2ExportGLB decimation_target=80000, texture_size=512,
remesh=True` from a single 512 px front crop. That is a "safe for 12 GB" profile, not a
quality profile.

Note: the Gemini *final* `male-goose.glb` is a different thing — a procedural
Blender build (`build_male_goose.py`), 131 parts, **137,236 triangles** in the GLB
(its README says 90,060; that figure is pre-modifier/pre-export and stale).

Lessons carried in from earlier goose work (BlenderMagic wardrobe / tandem rig):
- TRELLIS output is soft "melted" triangle soup with **baked shadows in the albedo**,
  floaters and drip strings. Fine as a sculpt/blockout, not as final topology.
- Garments generated separately and bbox-stacked clip and read as slop. Generate the
  **whole dressed character as one shape**, then split/retopo in Blender.
- Final game asset needs **retopo + normal/albedo bake** (target ~10–20k tris), not
  decimation of soup.
- GPU is a **12 GB RTX 5070 Ti Laptop**. VRAM OOM = 0x116 TDR = hard reboot. Every GPU
  job goes through a `nvidia-smi` preflight + ComfyUI `/free`; prefer fp8/nvfp4 weights.

---

## 1. Goal and acceptance criteria

Deliverable: `out/male-goose/` containing
- `male_goose_hi.glb` — best generated high-poly (reference/bake source)
- `male_goose_game.glb` — **one skinned-ready mesh**, clean retopo, **≤20k tris**, one UV set, 2K PBR
  (BaseColor/Normal/ORM), A-pose, feet on Z=0, +Y forward per three.js convention.
  Final game-unit height is **deferred** until the tandem bike scale is fixed (§9);
  model at real-ish scale (~1.8 m) and rescale at assembly.
- `male_goose.blend` — source scene with collections: `Gen` (raw candidates),
  `Hi` (cleaned sculpt), `Game` (retopo), `Bake`, `Lookdev`
- `renders/` — 4 orthographic turnarounds matching the sheet's panels + 3/4 hero
- `model-info.json` — tris, verts, bbox, texel density, source seeds/settings

Acceptance (reviewed by Pete against the sheet, side by side):
1. Silhouette matches FRONT/PROFILE/REAR panels (overlay diff ≤ ~3% of height at hat,
   beak tip, shoulder, coat tails, boot toe).
2. Readable details: bowler + black band, white cheek patch shape, bow tie, wing collar,
   waistcoat buttons, coat lapels, tail feathers under the vent, boot buttons, gloves.
3. No baked shadow streaks in the albedo; no floaters; watertight per part.
4. Rear is genuinely modeled (coat vent + tail plumage), not a mirrored front.
5. Loads in three.js (the game) with correct scale/orientation and ≤ 4 draw calls.

---

## 2. Toolchain — "latest" audit and target versions

| Tool | Installed now | Latest (as of 2026-10-10) | Action |
|---|---|---|---|
| Blender | 5.1.0 | **5.2.2** (5.2 LTS); 5.3 due Nov | **Upgrade in place** (winget) — replaces 5.1 |
| ComfyUI Desktop | app **0.9.4**, core 0.27.0 on :8000 | app **1.1.6** (Oct 3); core v0.39.0; native TRELLIS.2 since core 0.34 | **Replace/upgrade the Desktop app** |
| TRELLIS.2 | community node `ComfyUI-TRELLIS2` (custom ops) | **native in ComfyUI core** since Aug 22 2026 (Trellis2ShapeStage / TextureStage / UpsampleStage, BiRefNet + MoGe helpers, UV-unwrap + normal/AO bake) | Use native nodes |
| Hunyuan3D | `hunyuan_3d_v2.1.safetensors` (7.4 GB) + native `Hunyuan3Dv2Conditioning(MultiView)` nodes | **2.1 is the newest open weights.** 2.5 / 3.0 / 3.1 are hosted-only (no weights). | Add **Hunyuan3D-2mv** (multi-view) weights; 2.1 Paint for texture |
| Hunyuan3D-Part | — | P3-SAM (3D part segmentation) + X-Part, open | Optional, Phase 5 (split garments) |
| Pixal3D | — | native in ComfyUI with TRELLIS.2 | Optional third generator |

**ComfyUI decision (Pete, 2026-10-10):** upgrade the Desktop app in place to 1.1.6
(Pete uses it rarely). Keep `Documents\ComfyUI\models` as-is. If the bundled core is
still < 0.34 after upgrade, update core from inside Desktop. Consequence: the old
`ComfyUI-TRELLIS2` custom node and the BlenderMagic/Gemini scripts that call its nodes
(`Trellis2ImageToShape`, `Trellis2ExportGLB`, …) may break; this project uses only the
**native** nodes. Remove the custom node if it conflicts.
**Blender decision:** upgrade everything to 5.2.2. Old scripts that hardcode
`Blender 5.1.1\pythonin\python.exe` need the path bumped to 5.2.

Models to fetch (into the shared `models/` tree; ~30–40 GB free needed, 540 GB free):
- `Comfy-Org/TRELLIS.2` repackaged weights (shape + texture flow models, VAEs) —
  prefer fp8/bf16 split files sized for ≤12 GB
- `Comfy-Org/BiRefNet` (background removal), `Comfy-Org/MoGe` (FOV estimation)
- `tencent/Hunyuan3D-2mv` DiT (multi-view shape; front/left/back/right conditioning)
- `tencent/Hunyuan3D-2.1` paint model (if we texture with Hunyuan; needs wrapper node)
- Optional: `tencent/Hunyuan3D-Part` (P3-SAM), `Comfy-Org/Pixal3D`

Phase-0 verification: a 1-image smoke test on each generator at the lowest setting,
logging peak VRAM from `nvidia-smi` (not `/system_stats`, which under-reports).

---

## 3. Phase 1 — Reference prep (`scripts/prep_refs.py`, Blender python)

1. Crop the four male panels from `characters-turnaround.png` at full res (sheet is
   ~1375×1150, so each panel is ~340×490 — **too small**).
2. Upscale each crop 4× (ComfyUI upscale model, e.g. 4x-UltraSharp/ESRGAN) → ~1400 px
   tall; check the cheek patch / buttons survive without hallucinated detail.
3. Matte with BiRefNet → RGBA, centered, square-padded, white bg variant too.
4. Produce the **4 canonical views** for multi-view: front, left, back, and a
   **right** view (= mirrored left profile; acceptable because the costume is
   symmetric except watch chain/buttons — note any asymmetry).
5. Height-normalize all views so hat top and boot soles align on the same pixel rows
   (multi-view conditioning assumes consistent scale).
6. Optional "clean single image": regenerate a high-res 3/4 front A-pose render of the
   male with Z-Image (nvfp4 + fp8 CLIP, guarded runner) using the front view as
   reference — gives TRELLIS.2 one large, consistent, shadow-light input.

Outputs: `refs/male/{front,left,back,right,threeq}_{rgba,white}.png`.

---

## 4. Phase 2 — Generate candidates (two engines, small seed sweep)

All jobs submitted by `scripts/comfy_job.py` (ComfyUI API, VRAM preflight, `/free`
between jobs, resume manifest `out/male-goose/manifest.json`, one job at a time).

**A. TRELLIS.2 native (single image)**
- Inputs: front, threeq. Shape stage at 512 → **upsample stage to 1024** if VRAM
  allows (profile ladder: 512 safe → 1024 low-tokens → 1024 normal; never the 1536
  tier on 12 GB unless a smoke test proves headroom).
- Texture stage on, UV unwrap node, 2K texture, **no decimation at export** (keep the
  full mesh; we decimate/retopo ourselves).
- 3 seeds × 2 inputs = 6 candidates.

**B. Hunyuan3D-2mv (multi-view shape)**
- `Hunyuan3Dv2ConditioningMultiView` with front/left/back/right → the strongest bet
  for a correct rear (coat vent, tail) and profile (beak length, belly).
- Octree resolution 256→384 per VRAM; 3 seeds.
- Shape only; texture comes from step C.

**C. Texture the best untextured shape**
- Option C1: TRELLIS.2 **texture stage on an existing mesh** (its texturing pipeline).
- Option C2: Hunyuan3D-2.1 Paint (multi-view PBR) via wrapper node.
- Pick by: no baked shadows, cheek patch crispness, button/band legibility.

**D. Selection** (`scripts/review_candidates.py`, Blender 5.2 headless)
- Render each candidate in the 4 sheet views with an orthographic camera; composite
  side-by-side with the reference crop + silhouette XOR overlay; write a contact sheet
  `renders/candidates_contact.png` and per-candidate silhouette IoU score.
- Pete picks the winner (or a hybrid: e.g. Hunyuan-mv body + TRELLIS hat/head).

Expected: TRELLIS.2 wins on surface detail/texture; Hunyuan-mv wins on back/side
correctness. Plan assumes we may combine them.

---

## 5. Phase 3 — Hi-poly cleanup (`scripts/clean_hi.py`)

1. Import, apply transforms (glTF transform must be applied or local axes lie).
2. Orient: feet on Z=0, facing -Y (Blender) → +Z/−Z per glTF export setting; scale
   to agreed height.
3. Remove floaters (islands < N verts), drip strings (thin-component filter).
4. Voxel remesh (≈2–3 mm) to make it watertight, then Multires/sculpt fix-ups by hand
   where needed: beak tip, hat brim edge, bow tie, gloved fingers, boot soles.
5. Symmetrize where the design is symmetric (head, hat, legs) — **not** the coat front.
6. De-light the albedo: estimate and remove baked AO/shadow (Blender bake of AO from
   the mesh → divide/curves on albedo), or re-project texture from the reference
   views onto the cleaned mesh (`project_from_view`) for the front/side/back.

Output: `Hi` collection, ~300k–1M tris, clean texture.

---

## 6. Phase 4 — Game mesh (retopo + bake) (`scripts/retopo_bake.py`)

1. **One mesh** (decision): retopo the dressed character as a single continuous
   surface — clothing is part of the body shell, not separate layers. Use color
   sampling (method proven in BlenderMagic wardrobe) only to build **material
   masks / vertex groups** (hat, beak, eyes, coat, waistcoat, breeches, gloves, boots,
   tail) so regions stay identifiable for texturing and a future split.
2. Retopo: Quadriflow (or Instant Meshes) on the whole character, **≤20k tris**;
   denser on head/beak/hands, sparser on coat back; manual edge loops at
   elbows/knees/neck/shoulders/hips so it skins cleanly later.
3. UV: Smart UV + pack (or Blender 5.2 UV packer) into one 2K atlas, texel density
   checked.
4. Bake hi → game: Normal (tangent), BaseColor, AO, Roughness → pack ORM.
5. Export `male_goose_game.glb` (Draco off for now; game loader decides), verify
   re-import, write `model-info.json`.

---

## 7. Phase 5 — Validation and handoff

- Turnaround renders (`renders/male_{front,left,rear,threeq}.png`) on the sheet's
  off-white background, side-by-side with the ref crops → `renders/male_compare.png`.
- three.js check: load in a minimal viewer page (or the game's dev loader) to confirm
  orientation, scale, materials.
- Pete review → iterate Phase 3/4 only (don't regenerate unless silhouette fails).

Rigging/pedaling is **out of scope** for this plan; edge loops in Phase 4 keep it
possible (see BlenderMagic tandem-rig lessons for when that starts).

### Future / stretch goal — separate clothing meshes (costume swap)
Pete's wish: hat, coat, waistcoat, breeches, gloves, boots as separate meshes on a
shared rig so outfits can be swapped. Not now because it needs a body *under* the
clothes plus fitted, non-clipping garment shells (TRELLIS-per-garment was tried in
BlenderMagic and rejected as slop). Path when we get there:
1. Start from this plan's one-mesh goose + its region vertex groups.
2. Sculpt/derive a "naked" goose body under the clothes (shrink the clothed shell).
3. Garments = shells derived from the clothed surface (separate by vertex group →
   solidify → retopo), or Hunyuan3D-Part (P3-SAM/X-Part) to propose part splits.
4. Data-transfer skin weights from the body; test for clipping across the riding pose.
Easiest first wins: **hat** and **boots** (rigid, minimal deformation).

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| VRAM OOM → hard reboot | nvidia-smi preflight, `/free`, one job at a time, smoke-test each tier before use, never 1536 tier unproven |
| Sheet panels too low-res | 4× upscale + optional Z-Image re-render of a clean hi-res view |
| Profile ≠ front proportions (AI sheet inconsistency) | Hunyuan-mv honors all views; silhouette IoU per view tells us which view disagrees |
| Baked shadows in albedo | De-light step or re-project from refs; TRELLIS.2 PBR output is better than v1 here |
| Hunyuan 2.1 license excludes EU/UK/KR | Fine for Pete's US distribution; note it for Steam store territories |
| ComfyUI upgrade breaks old TRELLIS2 custom-node scripts | Accepted (Pete rarely uses Desktop); this project uses native nodes only; fall back to side-by-side install if Desktop 1.1.6 bundles core < 0.34 |

Time estimate: Phase 0 half-day (mostly downloads), Phase 1 ~2 h, Phase 2 ~half-day
(generation is minutes per job; review is the long part), Phase 3–4 1–2 days, Phase 5
~2 h.

---

## 9. Reuse for female goose and tandem bike

**Female:** identical pipeline with bottom-row panels. Differences: dress hides legs
(generate as one closed volume — don't try to model legs under the skirt), feathered
hat plume is thin geometry (expect TRELLIS to blob it → model plume as cards/alpha in
Phase 4), bustle/ruffle layers favor Hunyuan-mv for the rear.

**Tandem bike:** generators are weak on thin tubes and spokes. Use AI only for the
**blockout + brass/fender/saddle textures**; build the frame from curves/tubes, wheels
procedurally (rims, spokes, tires) using `bicycle-turnaround.png` orthos as image
planes. Saddles, chainrings, fenders, lamp can be generated parts. Agree world scale
(wheelbase) here first — it sets both geese's heights.

---

## 10. Decisions (Pete, 2026-10-10)

1. ComfyUI: **replace/upgrade the Desktop app** (side-by-side acceptable but not preferred).
2. Blender: **upgrade everything** to 5.2.2.
3. Game mesh budget: **20k tris**.
4. Final game-unit height: **deferred** until the bike scale is fixed.
5. Mesh structure: **one skinned mesh now**; separate clothing = future/stretch (§7).

## Female goose — progress (2026-10-10)
- Phase 1: `crop_panels.py female` (bottom row) + `comfy_job.py prep --char female` → `refs/female/prepped/`.
- Phase 2: Pixal3D multi-view, 1024 tier, 2K tex. ComfyUI restarted with
  `--disable-pinned-memory --cache-none` after Claude Code reaped it for **low system RAM**
  (the first sweep lost seed 2026 mid-run); peak GPU dropped 10.6 → 9.7 GB with those flags.

| Seed | Mean IoU (front/left/back/right) | Visual notes (`renders/f_closeup_seeds_1024.png`, `renders/f_closeup_123_vs_2026.png`) |
|---|---|---|
| 42 | 0.909 (.91/.90/.93/.89) | magenta/pink hat bow, olive "leaf" yoke, black spectacle-like frames around brooch, flesh blotch on back of neck, silver beak tip |
| 7 | 0.907 (.91/.89/.93/.89) | burgundy hat OK; plume dark & glassy (chrome highlights); loud orange yoke; silver beak patch |
| **123** | **0.912** (.92/.90/.94/.90) | **closest to sheet**: burgundy hat + rosettes, tan/brown plume, cream collar, clean gold brooch, subtle lace yoke. Iris yellow-green (should be brown) |
| 2026 | 0.911 (.91/.90/.94/.90) | best pleated peach lace yoke, nice bustle profile; but whole outfit shifts rose-pink, plume mauve, cartoon white-ring eye |

Female IoU tops out ~0.91 (vs male 0.94): skirt ruffles + thin plume are harder.
Recommendation: **seed 123** — Pete agreed.

- **Phase 3 done** — `clean_hi.py --char female` → `out/female-goose/female_goose_hi.glb` (489k tris,
  1.80 m incl. plume, 0.83 × 0.69 m). Fixes from `chars/female.json`: generic **`recolor`** plugin
  (new, `scripts/fixes/recolor.py`) — iris yellow-green → brown, 157 texels (v2 window: hue 50–165,
  val ≥ 0.05; v1 missed the darker right iris and read orange).
- **Facing heuristic removed** — the old "beak is the most forward point" check rotated her 180°
  (plume/brim reach further back than the beak forward). Orientation is now config
  (`"yaw_steps"` in `chars/<char>.json`, default 0 — Pixal3D always emits front = −Y); the
  heuristic only prints a warning (it does warn for her; expected).
- **Phase 4 done** — `out/female-goose/female_goose_game.glb`: **19,600 tris**, 1 draw call,
  2K BaseColor/Normal/ORM, 13.4 MB, validator 0 errors / 0 warnings, IoU 0.913 (= hi).
  Renders: `renders/f_game_v1_review.png`, `renders/f_closeup_hi_vs_game.png`, `renders/f_eye_fix.png`.
- **Shiny-surface audit** (per-face on game ORM): boots metallic 0.00, roughness ~0.68 (glossy
  leather, no chrome); body metallic max 0.22 (brooch). No boot fins — her boots are clean.

### Female goose — fixes needed (v1 → v2), logged 2026-10-10
| # | Issue | Where | Proposed fix |
|---|---|---|---|
| F1 | **Detached cream strip** hanging behind the cheek patch under the right hat brim — a thin torn sheet (same family as male M1 boot fins). | hi + game | `trim_fins` plugin (planned for M1) or manual delete; re-bake. |
| F2 | **Plume tips** ragged/torn and slightly glassy; game mesh softens the tips further. | hi + game | Rebuild plume as alpha-tested feather cards (PLAN §9 already predicted this). |
| F3 | **Hat underside / brim** shows layered semi-transparent shells and small dark-green specks on the brim front. | hi texture/geo | Inspect; recolor specks via `recolor` if they're not intended leaves; delete inner shells. |
| F4 | **Ankle-boot heels** read lower/flatter than the sheet's heeled ankle boots. | hi geo | Minor; sculpt heel if it matters at game distance. |
| F5 | **Eye whites** are a cartoon white ring around the (now brown) iris; sheet shows a mostly dark round eye. | texture | Optional `recolor` (white ring → dark) if Pete wants closer to the sheet. |
| F6 | Same as male: adaptive-triangle topology (M5), no region vertex groups (M6), not viewed in three.js (M8). | game | Shared follow-ups. |

## v2 fix pass — status (2026-10-10)
Both characters re-run end to end (`clean_hi.py` → `retopo_bake.py`) with all fixes from
`chars/<char>.json`. Both game GLBs: **19,600 tris, 1 draw call, Khronos validator 0/0**;
IoU male 0.938, female 0.913. Renders: `renders/{male,female}_game_v2_review.png`,
`renders/v2_closeups.png`, `renders/m_boots_v2.png`, `renders/f_strip_dryrun.png`.

New plugins (all dry-run capable where destructive):
| Plugin | Stage | What |
|---|---|---|
| `recolor` | hi | height band + HSV window → target colour, keeps shading |
| `material_override` | hi | set/clamp metallic & roughness in a region |
| `trim_fins` | hi | volume "opening" (voxelize, per-slice fill, ball opening via `uv run --with scipy`) deletes thin debris patches ≥ min area |
| `silhouette_carve` | hi | delete geometry outside the reference mattes — **tested, not used** (misaligns at frame edges: chopped male soles, flagged female beak) |
| `region_delete` | hi | explicit metre box + colour window; escape hatch for one-off debris |
| `region_groups` | **game** | vertex groups by baked colour + height (first stage-"game" plugin; hook in `retopo_bake.py`) |

| # | Status | Notes |
|---|---|---|
| M1 boot toe flaps | **Partly fixed** | `trim_fins` removed the thin flap tips (52 + 44 cm²). The rest is a *thick* flared sole → M3. |
| M2 chrome boots | **Fixed** | Two causes: metallic patches (max 1.0 → 0) **and** cyan/white reflections painted into the albedo (7.9k + 1.6k texels recolored to dark leather). |
| M3 toe shape / flared soles | **Open — sculpt pass** | Not safely automatable (thickness and silhouette tests both fail); needs an interactive Blender sculpt or a regenerated boot. |
| M4 coat-shoulder bake smudge | **Mostly fixed** | Bake cage extrusion 0.01 → 0.04 m, ray 0.03 → 0.1 m (new defaults, `--extrusion/--ray-dist`); one faint mark remains. |
| M5 quad topology | **Open — needs Pete's OK** | Instant Meshes (external binary). |
| M6 region groups | **Done (approximate)** | Male: hat, beak_head_neck_bowtie, cheek_patch, collar_shirt, gloves, boots, waistcoat, breeches, tail_feathers, coat, other. Tags are a starting point, not final cuts. |
| M7 hat colour | **Pete to judge** | Tunable in `chars/male.json`. |
| M8 three.js check | **Pete** | |
| F1 cheek strip | **Fixed** | `region_delete` (144 faces); box found by profiling cream faces by depth (+X side had a separate cream piece behind the cheek). |
| F2 plume | **Open — art task** | Rebuild as alpha feather cards. |
| F3 brim specks / layered brim | **Open — Pete to judge** | Specks may be intended ornament; layered shells are inside the hat. |
| F4 heels | **Open — sculpt pass** (minor) | |
| F5 eye whites | **Pete to choose** | Optional `recolor` if wanted. |
| F6 region groups | **Done (approximate)** | Female: beak_head_neck, cheek_patch, hat_plume, collar, brooch_lace, gloves, boots, dress, other. |

## v3 pass — Pete's answers (2026-10-10)

Pete: M5 approved Instant Meshes; M7 hat brown OK; F3 brim specks are **ornaments, keep**;
F5 eyes must **match the sheet and be identical on male and female** (needed for rigging/animation);
M8 Pete checked both game GLBs in Blender — "look really good".

| # | Status | Notes |
|---|---|---|
| M5 quad topology | **Tried — rejected for now** | Instant Meshes (wjakob, official Windows build in `tools/instant-meshes/`) wired in as `retopo_bake.py --remesher instant` (face-count calibration loop, hole fill, consistent winding). Pure quads at the 20k budget = uniform ~13 mm edges: it **fuses the coat skirt with the tail feathers** and chews the brim / sole edges, so the bake smears across layers (`renders/m5_instant_meshes_vs_decimate.png`). Adaptive QEM decimation stays the default. Revisit per body part (joints only) if skinning shows problems. |
| M7 | **Closed** | |
| M8 | **Closed (Blender)** | In-game three.js check when the bike/scale lands. |
| F3 | **Closed — intended ornaments** | |
| F5 / M9 eyes | **Done** | New stage-"game" plugin `eyes` + shared spec `assets/goose_eye.json`: one eyeball (R 16.3 mm, 16 seg, 2 × 114 verts, 224 tris) with a radial colour profile from the sheet (black pupil, brown iris → dark limbal ring, cream rim, dark lid line), glossy. Same spec, mesh and texels on every goose; only placement differs (per-char surface picks via `scripts/head_views.py --pick`, mirrored symmetric across each head). Painted eyes under the balls recoloured to head colour. Eyes join the single mesh (still 1 draw call) as vertex groups `eye_L` / `eye_R`; eyeball centres + look axes stored as object props `eye_L_center`, `eye_L_axis`, … and in `<char>_goose_game.json` → **eye bones pivot there**. Female `iris recolor` disabled (superseded). `renders/eyes_v3_vs_sheet.png`. |

Pipeline changes: `retopo_bake.py` reserves the top 16 atlas rows (`--reserve-rows`, obj prop
`uv_reserved_rows`) and 500 tris (`--reserve-tris`) for game-stage additions; game meshes are now
**19,558 tris** (19,110 body + 448 eyes), validator 0/0, 1 draw call. **Bug fixed:** bake images were
reused from the .blend and `pack()` kept the *previous run's* pixels, so a retopo+bake re-run without
`clean_hi` shipped stale textures on new UVs — images are now recreated every run.
Observation: both heads are yawed toward −X (male ~15°, female ~38°, as drawn on the sheet) — the
rig's neck/head bones should absorb this rest pose.

Still open: M3/F4 sculpt (toe/sole, heels), F2 plume cards, M1 remainder (→ M3). Then the bike.

## v2 pipeline — progress (2026-10-10)

Plan of record moved to `ROADMAP.md` (P0–P6). Reference set v2 in `refs/v2/` (Pete, Codex image_gen).
New char ids: `base` (unclothed shared goose), `outfit_male`, `outfit_female` (configs in `chars/`).

- **P0.1 done** — `scripts/crop_sheet.py <char>` crops labelled grid sheets (caption components painted
  out). Height spread across views: base 1.5 %, outfits 2.7 %; front L/R symmetry IoU base 0.936,
  male 0.927, female 0.826 (asymmetric plume/bustle, expected). Report: `refs/<char>/crop_report.json`.
- **P1.1 done** — `comfy_job.py prep --char base`: mattes clean incl. hands, webbed feet, tail
  (right = mirrored left for symmetry; drawn right kept as `right_drawn_raw.png`).
- **P1.2 running** — Pixal3D multi-view 1024, seeds 42 / 7 / 123 / 2026.
- **v3 references** (`refs/v3/`, Pete via Codex): 2x2 sheets, one master pose with arms that agree in every view.
  v2 gave every seed an extra hand per side (front vs side views disagreed). `check_hands.py` gate added.
- **P1.2 done** — v3 sweep: all 4 seeds pass the hand gate; IoU 42 0.936 / **7 0.940** / 123 0.931 / 2026 0.932. Pete chose **seed 7**.
- **P1.3 / P1.4 done** — `clean_hi.py --char base` (1 island, 1.65 m) + new `symmetrize` plugin: mirror plane yaw -0.25°,
  offset -1.3 mm; L/R deviation before 2.0 / 3.3 / 8.5 mm (p50/p95/max, ~vertex spacing) → 0 after. Kept −X half (+X hip
  had a stronger baked hand-shadow smudge).
- **P1.5 (first pass)** — Instant Meshes quads: **10,796 tris**, 1.65 m, validator 0/0, 1 draw call. Even quad grid; head,
  beak, body good. **Fingers fuse into mittens** at this budget with either remesher (fingers ~1 cm, touching); IM feet
  webbing blocky. Hands/feet are covered by gloves/boots in both outfits — Pete to decide (see issue #8).
- **P1.6 eye asset** — `scripts/make_eye_asset.py` → `assets/goose_eye/` (eyeball 440 + lids 2×320 + catchlight 8
  tris per eye; almond opening pointed toward the bill, iris rests 8° back so cream shows toward the bill; blink =
  lid rotation about the eye centre; catchlight static). Fitted by new game-stage plugin **`eye_sockets`**: per-texel
  painted-eye erase (`common.texel_positions`), local subdivide + rim-following socket (faces in front of the opening
  deleted, edge verts snapped to the rim, skin wrapped 0.75 mm over the lid shell), eyes as child objects *_L/_R
  with shared materials, lid colour matched to the head. Base game GLB **13,470 tris, validator 0/0, 9 draws,
  4 materials**. `glb_fix_tangents.py` now also drops unused tangents; MikkTSpace needs n-gons triangulated.
  Previews: `preview_eyes.py` (pre-integration), `eye_states_glb.py` (states on the final GLB).
- **P1.7 beak split** — new game-stage plugin **`beak_split`**: plane through the mouth line (tip [-0.2875, 1.500] →
  gape [-0.150, 1.522], ~30 % up the bill as in refs/v3) bisects the bill in front of the gape; cut edges split so
  the halves separate but stay joined at the mouth corners; roof/floor caps in a mouth colour (reserved atlas strip);
  vertex group `beak_lower` (face-side aware on the cut; fades 15 mm behind the gape); props `beak_hinge_point`,
  `beak_hinge_axis`, `beak_open_deg`. Preview `scripts/beak_preview.py`. Base GLB 13,548 tris, validator 0/0.
- **P1.8 lighting check** — `scripts/delight_check.py`: per colour cluster, luminance vs face normal-z and baked AO.
  Up-facing vs down-facing luminance differs only ~10-13 % (dark 0.144/0.117, brown 0.277/0.244, cream 0.695/0.624;
  light-brown reversed) and a lighting model explains R² 0.10-0.18 → **no de-light pass** (would flatten the painted
  feather-edge detail). The v3 references' flat lighting did its job. Also: `retopo_bake.py` now drops speck islands
  again after the quad remesh (Instant Meshes left two 7-vertex specks by a hand and a foot).
- **P1 complete** — base goose game GLB **14,166 tris**, validator 0/0: body (Instant Meshes quads), shared eyes,
  split beak + tongue + serrations. Rig data in object props / vertex groups (eyes, beak_lower, tongue).
- **P2 standard rig DONE** — `build_rig.py` (35 bones, Mixamo-style + Neck1-3, Jaw, Tongue, Left/Right Eye + Eyelids,
  Tail, HatSocket; joints measured from the mesh; hip joint 14 cm above the crotch per Pete), `skin_rig.py` (bone-heat,
  face bones excluded, jaw/tongue from P1 groups, ≤4 influences, eye parts bone-parented, skinned mesh as root node),
  `pose_test.py` (T / A / riding / neck / honk+blink: ≤1.1 % edges past 1.6× or 0.5×, all at the riding hip crease),
  `make_anims.py` (idle, blink, look_around, honk as NLA tracks), `tools/threejs_check/check.mjs` (headless Chrome +
  the game's three r161 from ../tandemonium/node_modules: 1 skinned mesh, 35 bones, 4 clips, every clip moves its bones).
  `base_goose_rigged.glb` validator 0/0.
- **P3.1 started** — `comfy_job.py prep --right drawn` option (female costume is asymmetric: drawn right view
  instead of mirrored left). Male + female outfit views prepped (mattes clean). The 8-run seed sweep was stopped by
  Claude Code's low-memory reaper before any run finished; restart from `RESUME.md` after the reboot.
- **P3.1 DONE (2026-10-10)** — 8-run Pixal3D sweep (seeds 42/7/123/2026 per outfit, ~3 min each, no reaps after reboot).
  Male mean IoU 0.943/0.931/0.931/0.943, all 1 glove per side. Female 0.924/0.925/0.925/0.921; s42 hand check
  false-negative on +X (glove visible), s42 peach cheeks/collar. Close-ups: `renders/outfit_{male,female}_closeups.png`.
  **Pete picked male s2026** (clean bowler, bow tie, boots; tiny cufflink blob) and **female s7** (best 3-tier bustle,
  cream cheeks; right boot smeared to a point — fix at garment stage, or borrow s123's boots). `clean_hi.py --height 1.65`
  (provisional = base height; P3.2 sets real scale) → `out/outfit_{male,female}-goose/outfit_*_goose_hi.glb` (IoU unchanged).
- **P3.2 first pass (2026-10-10)** — `scripts/align_outfit.py`: trimmed similarity ICP, base bill/face/neck anchors
  (z > 0.80 H, up to the bill-tip height: `--crown 0.0`; 0.05 let the hat brim in and skewed the fit) → outfit nearest
  surface. Outputs `out/<char>-goose/<char>_goose_aligned.glb`, `<char>_align.json`, `renders/<char>_align_{overlay,dist,head}.png`.
  **Male:** scale 1.032, rot < 0.5°, anchor residual median 1.5 mm / p90 3.7 mm, boot soles 7.5 mm below the floor → one
  similarity fits head AND feet. **Female:** head fits (bill 2.1 / 5.1 mm) at scale 1.104, but her feet land 8.5 cm below
  the floor and her torso/arms are slimmer than the base → her clothed body has a smaller head-to-body ratio; one rigid
  transform can't fit head and body. Both: the generator "paints" clothes tight on the body (male: 36 % of outfit
  surface within 5 mm of the base) and the base body pokes out (thighs, tail through the jacket back, webbed feet past
  the boots) → pure distance-to-body extraction (P3.3) will not separate garments; needs texture/region segmentation.
- **Poke-through measured** (`scripts/poke_depth.py`, body points >3 mm outside the aligned outfit): male torso 77 % (median
  13 mm, p90 26), thighs/hips 71 % (13 / 59, max 122 = tail through jacket back), hands 58 % (9 / 18), boots 62 % (8 / 16),
  feet 60 % (11 / 45). Female feet/shins median 28–44 mm (feet 8.5 cm low). Base body ≈ 1–1.5 cm thicker than the
  generator's under-clothes body. Pete: **rig-fit + per-bone girth scale, then P3.4 shell offset + P3.5 body masks.**
- **P3.2b rig-fit (D9)** — `scripts/rig_fit.py`: inequality ICP per bone on the skinned base game mesh. Correspondence
  along vertex normals (nearest-point snapped to the wrong wall of the ~5 mm double-walled shells); covered points stay
  put (the hidden body under loose cloth is unknown), points poking out / within 2 mm move 2 mm inside; fit = linear LSQ
  → rotation (≤15°) × length × girth (≤1, ≥0.55); kept only if it beats identity. Torso girth-only (head fit holds), Tail
  fitted (tucks), boot landmark (near-black albedo: sole + ankle shaft) re-aims/stretches the legs. Poke metric: no outfit
  within 0.3 m along the outward normal (head/neck control 4 %). Male after: hands 22→3 %, boots 11→3 %, torso 14→5 %,
  thighs/hips 40→26 % (tail stub), feet 31→18 % (webbed toes); boot offset ≈0 (sanity). Female: boots 77 mm lower, 4–5 cm
  back → legs ×1.17–1.19; torso 33→6 %, hands 29→3 %, feet 41→14 %. Bugs fixed on the way: child head of unconnected
  bones must be the parent-transformed rest head (not the parent's tail).
- **P3.3 garment extraction (D10)** — `scripts/garment_explore.py` (per-face albedo → Lab k-means palette; body region =
  dominant bone of the nearest rig-fitted base vertex; `<char>_faces.npz`) + `scripts/extract_garments.py` (colour family
  cream / black / red / brown / tan / dark × region rules in `chars/<char>.json` "garments", with z / y / L / distance-to-body
  gates; 2 rounds of area-weighted majority smoothing). Male: hat 2.3 %, coat 42.5 %, waistcoat 4.3 %, shirt 1.4 %, bowtie
  0.5 %, gloves 4.8 %, breeches 21.6 %, boots 14.6 %, body 7.8 %, unlabelled 0.1 %. Coat vs breeches needed height bands +
  stand-off distance (coat tails stand off the body; shadowed breeches read coat-brown). Female (region does the work, the
  whole dress is one red): hat 4.8, bodice 6.3, sleeves 10.4, skirt+bustle 67.5, collar 0.4, gloves 1.7, boots 4.2, body 4.8 %.
- **P3.3 cleanup round (Pete: "clean up more")** — new gates: `layered` (ray inward finds another surface 8–45 mm behind,
  past the ~5 mm double wall = outer layer: coat tails over breeches, bow tie over collar), `ax_max`, `y_max`, `L_min`;
  hat = anything above z 1.60 + head faces ≥2 cm off the fitted head; waistcoat button column rule. Island merge:
  same-label components < 4 cm² join their main neighbour (detached pieces like buttons vote by nearest faces), then a
  piece-level pass < 15 cm² (40 cm² swallowed glove fingers). Layered-tan-torso → coat was tried and reverted (the
  waistcoat is "layered" too). Mid-split pieces in chars json "pieces": male hat 3.2 / coat 45.7 / chest 6.1 / breeches
  18.1 / gloves 4.4 / boots 14.9 / body 7.1 %; female hat 5.3 / dress 84.3 / collar 0.5 / gloves 1.5 / boots 4.1 / body 4.2 %.
- **P3.3 round 2** — added `inside_of` gate (strictly inside another garment's front x-extent per 2 cm band) to turn
  shadowed waistcoat creases from coat → waistcoat: at 5–95 % it grabbed the lapels (tan lapel highlights widen the
  extent), at 20–80 % it fragmented the bow tie / shirt V → reverted for the male (gate kept, unused). Female: red in
  head → hat (no change visible: the remaining hat flecks are the dark band/brim underside tight to the head).
  Rule-based colour labelling is at its limit on baked-shadow albedo; next lever = project 2D garment masks from the
  clean reference views (segmentation on refs/<char>/prepped) onto the mesh, or hand touch-up.
- **P3.3 reference masks (Pete chose)** — `scripts/ref_project.py` (Blender: per face, visibility + pixel in each prepped
  view via review_candidate's height/bottom/mass-centre normalisation; 91–96 % of visible area lands on the matte) →
  `scripts/sam_masks.py` (ComfyUI venv, transformers Sam2 + facebook/sam2.1-hiera-large, 856 MB in the HF cache; seeds =
  farthest-point interior samples of the rule-label splat, negatives from neighbours; one call per view, per-pixel argmax
  logit; facing-weighted votes) → `extract_garments.py --use-ref` (take SAM label if weight ≥ 0.5, ≥ 60 % agreement,
  colour family allowed by that garment's rules, face not from a `lock` rule; then across-shell copy ≤ 6 mm and 6 rounds of
  neighbour propagation). Gloves/boots rules locked; female non-cream hand = gloves. **Result: SAM masks are crisp on the
  refs, but votes reach ~1/3 of faces; leftovers sit where no view sees squarely (double-wall inner faces showing through at
  creases, edge-on folds, vent lining).** Male ≈ rules-only (fewer chest strips, new vent slivers); female slightly cleaner.
  Compare `renders/outfit_<x>_pieces_rules_vs_sam.png`.
- **P3.4 step 1 transfer** — `scripts/transfer_garments.py`: outfit verts take K=4 IDW skin weights from the rig-fitted
  base, then the blended per-bone inverse → base rest frame; per-piece GLBs in `out/<char>-goose/pieces/`. Male: moved
  median 7 / p90 24 mm, poke = rig-fit numbers (tail untucked again in rest → P3.5 mask), looks right. **Female: moved p90
  135 / max 300 mm** — skirt verts inherit LEG weights so the inverse leg stretch (×1.18) squashes/flares the skirt;
  arm girth 0.55 inverts to ×1.8 → puffy sleeves, huge gloves. Design question raised: inflate clothes to the shared base
  body (D9 as decided) vs a per-character body shape (female = base mesh + "female" morph/bone scales from the rig-fit).
- **D11 (Pete)** — per-character body shape: female = shared base mesh + rig deformed by her rig-fit (own joints, slimmer
  arms, longer legs; one topology, same weights/bone names → clips stay shared); male stays on the base (D1).
  `chars/outfit_female.json "body_shape": "fitted"` → transfer_garments keeps her clothes in place and checks them against
  the fitted body: poke torso 5.5 %, hands 4 %, boots 6 %, feet 14 % (toes → mask). Pete: SAM labels "fairly accurate";
  idea logged: a three.js page to paint/fix cut lines by hand if needed.
- **P3.4 shells (male, 8 pieces per Pete)** — `scripts/build_shell.py`: solidify 4 mm (cut pieces are open sheets: voxelising
  them leaked holes, 198 islands) → voxel 2.5 mm → drop islands < 3 % of the largest (mislabelled fragments) → QEM to budget →
  push-out to 3 mm over the body minus tail/hands/feet (only pieces that follow the body; gloves/boots/hat/bowtie
  `--no-push`: pushing gloves out of the mitten hands crumpled the fingers), capped at 30 mm and re-clamped along the
  normal (snapping to the nearest point jumped sideways, 145 mm) → smart UV → Cycles bake base colour + normal (1024²).
  Tris: coat 5880, breeches 2450, gloves 2940, boots 1568, waistcoat 882, hat 784, shirt 490, bowtie 196 = 15.2k (+ body
  12k before P3.5 masks). `scripts/assemble_outfit.py [--green]` renders the set. Reads well; leftovers: base tail through
  the vent, base chest through the waistcoat V, bake speckle (shirt patches, cream flecks on the waistcoat) → P3.5 masks.
  Pete idea: female shape as a few symmetric sliders (arm / torso / leg girth, leg length, height) instead of per-bone fit.
- **Female body sliders (Pete's idea, replaces her per-bone fit)** — `scripts/bodyshape.py` (shared: sliders → per-bone maps
  in the rig_fit format; `body_transforms()` / `deform()` for every outfit script) + `scripts/shape_preview.py` (base | rig-fit
  | sliders, and slider body inside the outfit + outside share). chars/outfit_female.json "shape": arm_girth 0.58,
  torso_girth 0.85, hip_girth 0.95, leg_girth 0.70, leg_length 1.15, leg_pitch 3° (her boots sit 4–5 cm behind the base
  feet; the pitch rotates the whole leg chain, children inherit it), height 1.0. Outside-share vs rig-fit: torso 10.6 vs
  11.6 %, thighs/hips 5.5 vs 5.8, boots/shins 8.0 vs 7.4; hands 12 vs 6 and feet 44 vs 18 (both replaced by gloves / boots).
- **Female on sliders + shells** — chars json `"body_shape": "sliders"`; transfer = inverse rig-fit → forward sliders (shared
  `bodyshape.py`, also used by build_shell / assemble). Loose cloth hangs from the pelvis: outfit verts 1.5–3.5 cm off the
  body blend their weights to Hips (leg weights round-tripped through two leg maps flared the skirt hem; 35 % of her verts,
  6 % of his). Female shells: dress 8820, gloves 2940, hat 1800, boots 1568, collar 392 = 15.5k. Male shells rebuilt after the
  loose-cloth change (15.2k). Both read well; leftovers for P3.5: wrists / feet / tail / chest V.
- **P3.5 first pass** — `scripts/dress_goose.py`: base_goose.blend (skinned body + rig + eyes) → worn shape (bodyshape:
  edit bones + rest mesh) → masks (body vert covered if a normal ray hits a shell ≤ 6 cm, face hidden if all 3 covered;
  forced: gloves→Hand, boots→Foot/Toe, coat→Tail, dress→Tail+legs) → body split into toggle sub-meshes keyed by the hiding
  pieces → shells skinned by Data Transfer (nearest face interp.), loose cloth → Hips **only for coat/dress** (on boots and
  baggy breeches it tore the riding pose), 6 rounds of edge smoothing, 4 influences, normalised → `<char>_dressed.glb/.blend`
  + `renders/<char>_dressed_poses.png` (rest, A, riding, neck). **Dressed visible tris: male 17.7k, female 18.2k (≤ 20k).**
  Rest / A / neck clean for both; riding: male coat skirts over the lap rough, female skirt cannot follow the thighs →
  D4 bone chains next.
- **D12 (Pete): cloth chains, front follows the thighs** — dress_goose pass B: hanging pieces (coat, dress) get chains
  Cloth_<piece>_<FL|FR|SL|SR|BL|BR>_<1..3> (parent Hips) placed from their loose verts (sector centroids at 4 heights,
  1 cm in); loose verts weight to the two nearest chains by angle and to neighbouring bones by height. Runtime rule
  (glTF has no constraints; the game implements it, `<char>_cloth_chains.json`): chain bone j takes slerp(Hips Δrot,
  thigh Δrot, follow × drape[j]) in armature space, follow F .7 / S .35 / B 0, drape [1, .45, .15] so the hem bends at the
  knee and hangs. Female: 6 chains, riding skirt drapes over the knees; male: 4 (coat fronts/sides; tails stay on Hips).
- **Dressed GLBs in-engine** — dress_goose export = make_anims settings (skins, tangents, NLA-track clips, Y-up) +
  glb_fix_tangents; shells no longer parented to the rig (skinned meshes must be root nodes). **glTF validator 0 errors /
  0 warnings** (male 34.5 MB, female 26.3 MB, 9 clips each). `tools/threejs_check/check.mjs <glb> <png> [chains.json]`
  now applies the D12 follow rule after each pose, as the game will (world-space slerp of the Hips/thigh rotation
  deltas × follow × drape, root first): the game's three.js r161 shows rest / T / A / riding / neck / honk correctly for
  both; the female riding skirt drapes over the knees exactly as in Blender.
- **Polish pass 1** — build_shell: chars json "shell_tris" (hats: male 1470, female 2450), "shell_mirror" (female boots
  rebuilt from the good +X boot), colour baked from the whole `<char>_outfit_on_base.glb` instead of the piece.
  Hats / boots better; **the waistcoat cream patches and breeches tan flecks did NOT change** → they come from the
  generator's own albedo (or the bake cage hitting the inner shell wall), not from piece holes. Next lever: texture
  clean-up per piece (inpaint flecks by garment colour stats) or a bake from the inner/outer wall only. Dressed
  visible tris: male 18.4k, female 18.2k; validator 0/0, three.js ok.
- **Polish pass 2 (Pete: clean textures, hide the tail, clean bow tie / brooch collar)** —
  - *Textures:* build_shell bakes colour from the piece again (the whole-outfit bake leaked the coat onto the waistcoat
    sides); bake misses come out pure black and `tex_clean.py` (scripts venv: numpy/scipy) repaints them from the same
    UV island, plus texels nearer a *foreign* garment colour (chars json "shell_clean": medians from `<c>_faces.npz`,
    round blobs kept = buttons). Waistcoat 15 % miss + 20 % foreign repainted (coat-brown sides gone, buttons kept),
    breeches / coat / shirt / dress likewise. Colour is now even; what is left is **geometry**: overlapping shards of the
    generated shells shade as dark / light patches (waistcoat V, breeches seat, coat hem).
  - *Tail:* dress_goose FORCE breeches → Tail too (the reference male has no tail showing). build_shell "shell_fill"
    closes the breeches seat over uncovered Hips / Tail faces (tail pulled into its root, offset to the piece's median
    clearance), and the waistcoat chest below the V (the goose's light breast showed through its holes).
  - *Neckwear modelled (make_accessory.py):* male bowtie = cream standing collar with wing tips, black neck band, cream
    V shirt front, butterfly bow + knot, placed at the neck base (side-radius flare test) with colours from refs/v3.
    Female collar = scalloped cream standing collar + gold dome brooch; the terracotta scalloped bib and the round
    dress-red collar are part of the dress (Pete) → `shells/dress@bib.glb`, joined into the dress by dress_goose.
    "accessory_clear": dress_goose deletes faces of coat / waistcoat / shirt (male) and dress (female) whose radial line
    meets the modelled parts within 2.5 cm — the old bow / collar fragments.
  - Pete: new dress and brooch / necklace / collar designs are needed so the artifacts separate cleanly (design work, his).
  - Dressed visible tris: male 19.5k, female 20.2k (collar + bib 2.8k; slightly over the 20k budget). Validator 0/0,
    three.js ok (chains 4 / 6). Review: `scripts/dressed_closeup.py` (toggle pieces, ortho close-ups).
- **Polish pass 2b (Pete: vest front only, split bow tie / shirt, coat + breeches hang over the tail)** —
  dress_goose masks also hide body faces with a shell up to 1.5 cm *behind* them (body poking through the vest);
  build_shell "shell_keep" (vest: front ±55°, ≤ 2.5 cm off the body: back strap / flyaway shards gone);
  make_accessory "accessory_split": bowtie = bow + knot + neck band, collar / wing tips / V shirt front →
  `shirt@collar.glb` (joined into the shirt). "shell_hang": the back sector of the breeches (crotch → tail root
  + 9 cm, ±65° about the back) and coat (hem → tail root + 8 cm, hanging = radius never shrinks downwards) is rebuilt
  as a smooth grid around the body with the tail pulled 60 % into a rounded stub; the coat skirt now falls over it.
  tex_clean fills wide repainted areas with a tiled fabric swatch of the garment (largest clean square) instead of
  nearest-texel streaks. Still rough: vest V edge shards, coat vent edge strips, breeches side shards.
  Dressed visible tris: male 19.0k, female 19.8k; validator 0/0, three.js ok.
- **Breeches-only check (Pete)** — `dressed_closeup.py --hide <all but breeches>` showed the generated waistband ragged
  and holed (it was hidden under the vest) and the rebuilt seat reaching 0.99 m (it read as a vest back). The breeches
  are now rebuilt as a full ring ("shell_hang" az 0–360, "z_top" 0.91 = 5 cm above the vest's 0.86 hem, down to the
  crotch + 2 cm, 1 cm off the body, tail stub 85 % pulled); everything of the piece above the band is dropped. Clean
  waistband all round; left: jagged seam at the crotch line, swatch-tile patches, shards on the back of the thighs.
- **Designed breeches (Pete: one full, reusable piece of clothing; naked goose + green base; recolour)** —
  `scripts/make_garment.py` (chars json "garment_design") builds the garment from the BODY, with the extracted piece
  only as a shape guide: body band welded (glTF splits it at UV seams) → tail off and its hole capped on the closed body
  → cut at a tilted waist line (0.91 m front, rising 0.3 m/m to cover the tail base at the back; a level cut left a
  hole once the tail is hidden) and 0.385 m (inside the boots) → one surface through the crotch → Taubin-smoothed →
  ease = the piece's outer surface along the normal (jodhpur flare), smoothed, tight waistband / knee band, ≤ 40 % of
  the gap to the other thigh and clear of the hands, seat bump → game mesh 2548 tris; detail mesh (142k verts) with
  waistband / knee band, fly placket, slit pockets, side seams, inseams, front creases, centre seams, irregular folds
  above the knee → normal map + neutral tweed detail texture × one baseColorFactor (glTF), so a recolour is one value.
  Skin: the body's own weights carried through the subdivision (`breeches_weights.npz`; Tail merged into Hips),
  20 smoothing rounds. dress_goose: designed garments hide exactly their body band ("covers", 1.2 cm under the waist
  line) instead of ray masks; **all shells: weights averaged across UV-seam duplicate vertices** (they drifted apart
  in the smoothing and the seams opened in poses — the riding-pose holes). Tan / navy / olive and riding pose clean.
  `dressed_closeup.py --only <piece> --tint piece=r,g,b --pose riding`. Validator 0/0, three.js ok.
- **Designed shirt (Pete: full sleeves + cuffs, plain front, collar may change, tucked)** — make_garment kind "shirt":
  cut planes = neck base 1.28 m, tilted hem 0.85 m (6 cm inside the breeches line, same 0.3 rise), both wrists (Hand
  joint, plane ⟂ forearm); ease by rule (torso 7 mm, sleeves 11 mm + 6 mm blouse above a 5 mm cuff, 3 mm at the neck,
  4 mm at the hem); detail: button placket + buttons every 6.5 cm, side seams, armhole seam, sleeve underseams, 4.5 cm
  cuffs with cufflink, gathers above the cuffs, inner-elbow folds, blousing at the tuck. Cotton detail texture,
  colours cream / white / blue. Collar + wing tips stay modelled (`shirt@collar`), the old V shirt front is dropped
  ("accessory_drop"). Generic: every designed garment writes `<piece>_covers.npz` (exact body vertices it hides).
  **Layering (dress_goose):** a designed garment is a complete piece; faces with another shell in front (≤ 6 cm) or
  just behind (≤ 2 cm, poking through) are split into sub-meshes "<piece>__<a+b>" hidden while a/b is worn
  (LAYER_IGNORE: shirt ignores bowtie / gloves / breeches; breeches ignore the shirt); "tuck": the shirt torso below
  the breeches waist line − 1.2 cm is hidden while the breeches are worn (a clean line, no jagged hem). The game must
  toggle these like the body sub-meshes. Male dressed visible 18.0k tris; validator 0/0, three.js ok.

