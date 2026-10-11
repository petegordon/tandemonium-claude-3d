# RESUME — where we are and how to pick up (updated 2026-10-10)

Repo: https://github.com/petegordon/tandemonium-claude-3d (public). Plan of record: `ROADMAP.md`
(phases P0–P6, one GitHub milestone per phase, issues titled `[Pn.m]`). Pipeline manual +
progress log: `PLAN.md`. This file = the exact restart state.

## Status

| Phase | State |
|---|---|
| P0 reference intake | **Done.** v3 sheets in `refs/v3/` (Pete, Codex image_gen; consistent arms in every view). v2 superseded (it caused an extra hand per side). |
| P1 base goose | **Done.** Release `base-goose-p1`. Seed 7, symmetric, Instant Meshes quads, mitten hands (D8), shared eye asset in carved sockets, split beak + hinge + mouth + movable serrated tongue. |
| P2 standard rig | **Done.** Release `base-goose-p2-rigged` (rigged GLB + `base_goose.blend`). 35 bones, hip joint 14 cm above crotch, clips idle / blink / look_around / honk + one-frame `pose_*` clips; verified in the game's three.js r161. |
| P3 outfits | **In progress — P3.2 next.** P3.1 done: Pete picked **male s2026**, **female s7** (sweep notes in PLAN.md). Cleaned hi meshes `out/outfit_male|outfit_female-goose/outfit_*_goose_hi.glb` (provisional height 1.65 m). Known flaw: female s7 right boot smeared. |
| P4–P6 | Not started (bike reference needs Pete's fixes first). |

Pete's decisions so far: D1 male/base defines scale · D2 eyes from the reference, identical on all geese ·
D3 new standard rig · D4 skirt/coat tails = bone chains + weight painting · D5 wardrobe before riding ·
D6 one shared base body · D7 v3 references are the source of truth · D8 mitten hands ·
bind pose = model rest pose · Mixamo-style bone names · hip joint 14 cm · eye/beak/tongue looks approved.

## Machine setup (Windows 11, laptop RTX 5070 Ti 12 GB, 32 GB RAM)

- **Blender 5.2**: `"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"` (run scripts with `-b --factory-startup --python <script> -- <args>`).
- **Python for helper scripts** (PIL/numpy/scipy): `/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe`. System `python` is a WindowsApps stub — don't use it. `uv` is available for one-off deps.
- **Claude's ComfyUI** (not a service; start it each session), from Git Bash, in the background:
  ```
  cd /c/Users/pete/ComfyUI-claude && .venv/Scripts/python.exe main.py --listen 127.0.0.1 --port 8189 \
     --extra-model-paths-config extra_model_paths.yaml --disable-pinned-memory --cache-none > comfy-8189.log 2>&1
  ```
  Wait until `curl -s http://127.0.0.1:8189/system_stats` answers.
- **Never touch Antigravity's Desktop ComfyUI on :8000** (Pete's other agent uses it; never POST /free to it).
- **GPU/RAM:** 1024-tier Pixal3D needs ~9.5 GB free VRAM → Pete's Blender GUI closed and :8000 not running.
  System RAM: close the ChatGPT app / browsers before long sweeps; Claude Code kills background jobs under
  memory pressure (env `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` turns that off). Never auto-restart a
  reaped job — ask Pete.
- **glTF validator:** Node package in `%TEMP%/gv` (`npm i gltf-validator --prefix "$TEMP/gv"` if it's gone).
  Usage: `node -e "require(process.env.TEMP+'/gv/node_modules/gltf-validator').validateBytes(...)"`.
- **three.js check:** `node tools/threejs_check/check.mjs <glb> renders/x.png` (uses `../tandemonium/node_modules/{three,puppeteer}`; nothing in that repo is modified).
- **Instant Meshes:** `tools/instant-meshes/Instant Meshes.exe` (gitignored; `scripts/fetch_instant_meshes.sh` re-downloads).
- Local-only outputs (gitignored): `out/` (base goose .blend/GLBs, candidates) and `renders/`. Key ones are
  also on the GitHub releases.

## Next steps (P3.2 → P3.3)

Steps 1–4 below are DONE for P3.1 (kept for re-runs); resume at step 5.

1. Start ComfyUI (above), confirm ~10 GB free VRAM (`nvidia-smi`), Blender closed.
2. Seed sweep (background; ~3 min per run):
   ```
   for c in outfit_male outfit_female; do for s in 42 7 123 2026; do
     /c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe scripts/comfy_job.py pixal-mv --char $c --seed $s; done; done
   ```
3. Per candidate: copy `out/<char>-goose/pixalmv_s<seed>_*/textured_00001_.glb` →
   `out/<char>-goose/candidate_pixalmv_s<seed>_1024.glb`, then
   `blender ... scripts/check_hands.py -- <glbs>` (expect 1 gloved hand per side),
   `blender ... scripts/review_candidate.py -- <glb> --char <char> --out renders/<char>_c_s<seed>.png` (silhouette IoU),
   `blender ... scripts/closeup_compare.py -- renders/x.png <glbs...> --shots yaw:zc:scale,...` (hat, gloves, boots, bustle, coat tails).
   **Pete picks one seed per outfit.**
4. `clean_hi.py <candidate> --char outfit_<x>` (height from the base goose — P3.2 aligns scale using head/neck/bill).
5. P3.2 align each clothed model to the base body (head/neck/bill as rigid anchors); P3.3 garment extraction
   by distance-to-body → per-garment shells → bake from the clothed hi mesh (see ROADMAP P3).

## Base goose rebuild chain (if anything upstream changes)

```
clean_hi.py out/base-goose/candidate_pixalmv_s7_1024.glb --char base     # hi + symmetrize (chars/base.json)
retopo_bake.py --char base --tris 12000 --remesher instant              # game mesh + eye_sockets + beak_split
build_rig.py --char base [--render]                                      # skeleton (hip offset 0.14)
skin_rig.py --char base                                                  # weights, eye parts on bones
make_anims.py --char base                                                # clips + pose_* clips -> base_goose_rigged.glb
pose_test.py --char base ; node tools/threejs_check/check.mjs out/base-goose/base_goose_rigged.glb renders/base_threejs_check.png
```

## Gotchas learned (don't relearn them)

- n-gons (after bisect/subdivide) silently drop tangents on export → triangulate faces > 4 verts.
- glTF import sets quaternion rotation mode; set `rotation_mode = "XYZ"` before posing with Euler.
- Bone-local axis signs: Jaw local −X opens, Tongue +X lifts / +Y slides out, EyelidUpper −X closes,
  EyelidLower +X closes (recorded in `out/base-goose/base_rig.json`). Always check direction visually.
- Reused bake images keep stale packed pixels → `fresh_image()` in retopo_bake.
- Colour strips in the atlas must be tall (64 rows) or they blur to black in-engine (mipmaps).
- Instant Meshes can hang (120 s timeout + retry) and leaves tiny islands (dropped after remesh).
- Test in three.js, not just Blender: lighting/mipmaps/back-faces differ.
