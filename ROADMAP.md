# Tandemonium geese — roadmap

Where the Victorian Canada-goose characters go after v3, and how the pieces depend on each
other. `PLAN.md` is the pipeline manual and progress log; this file is the plan of record.
Each numbered item is a GitHub issue (`[n.m]` in the title); each milestone is a GitHub milestone.

## Where we are (v3, 2026-10-10)

- Male (seed 42) and female (seed 123) generated with Pixal3D multi-view from
  `refs/characters-turnaround.png`, cleaned by fix plugins, remeshed + baked to **one mesh each:
  19,558 tris, 1 draw call, glTF validator 0/0**, A-pose. Pete: "look really good".
- Repeatable pipeline: `comfy_job.py` → `clean_hi.py` → `retopo_bake.py`, per-character config in
  `chars/<char>.json`, fix plugins in `scripts/fixes/`.
- Already in the game (separate, older line — "Track 1"): one fused 500k-tri bike + both riders,
  39-bone lean rig, behind the *Show Riders* option. A modular "Track 2" discovery (bike + goose +
  show/hide garments on a 24-bone rig) lives in `BlenderMagic/`. Lessons from both are folded in below.

## Goals

1. **Reuse** — one goose "species": same body, skeleton, eyes, beak, feet, palette and animations
   for male and female (and any future goose).
2. **Change clothes and colours** — outfits as separate meshes swapped at runtime, garments
   recolourable.
3. **Ride the tandem** — both geese seated, pedalling, leaning; in the game.

## Architecture: one goose, many outfits

Canada geese look alike regardless of sex, and Pete wants identical eyes and shared rigging. So
the character is **one base goose body** (head, neck, eyes, beak, feathers, legs, feet) on
**one standard rig**, and "male" and "female" are **outfits** (+ hat) worn over it. A female
shape key (waist/chest) is optional. The generated v3/v4 meshes stop being the characters' bodies:
they become the **look reference and bake source** for each garment.

The male's generated body is the reference for scale and proportion (D1). The base body has
the clothing shape removed (1.0); the clothes come back as separate garments built over it (M4).

```
M1 Foundation (base body, eyes, beak, scale) ──► M2 Standard rig ──► M4 Wardrobe + colours ──► M3 Riding ──► M5 Delivery
```

Order changed by Pete (D5): wardrobe and colour changes come **before** riding in the game.

## M1 — Foundation

| # | Item | Size | Notes |
|---|---|---|---|
| 1.0 | **Base goose body — remove the clothing shape** | L | Undressed goose in A-pose: head/neck/beak/eyes from the v4 male (already good), body/arms/legs/feet underneath the clothes. Candidates: (a) the July `goose_naked` mannequin (evaluate first), (b) Pixal3D from an unclothed concept image of the same goose, (c) sculpt down from the v4 male. Proportions from the male (D1). |
| 1.1 | **Scale from the male** | S | **D1 decided:** the male defines scale (his body, not his hat). Base body inherits it; garments fit it. Absolute game height is a single uniform scale set with the bike in M3. Female mesh rescaled to the male's eye height for baking. |
| 1.2 | **Straighten the head** | M | Generated heads are yawed toward −X (male ~15°, female ~38°, as drawn). Plugin `head_straighten` (neck pivot, smooth falloff down the neck, hat turns with the head) on both v4 meshes, so the base head and both hats bake straight. |
| 1.3 | **Symmetry** | S | Base body mirror-symmetric (mirror the better half where needed) — required for mirrored weights. |
| 1.4 | **Species palette** | S | One feather black / cheek cream / beak grey on the base body; garments keep their own colours (M4). |
| 1.5 | **Reusable eye asset (eyeball + lids)** | M | **D2 decided:** take the oval opening, eyelids and colours from the reference sheet. Script-built: eyeball (sclera/iris/pupil + glossy cornea), upper/lower lid shell forming the almond opening, catchlight fixed to the lids, eye bones + blink. Own small shared material. Standalone close-up vs the sheet for Pete before it goes on the head. |
| 1.6 | **Split the lower beak** | S | Lower mandible + hinge for honk/quack. |
| 1.7 | **Armpit / hand clearance** | S | Arms and hands free of the torso so skinning won't tear. |
| 1.8 | **Joint density** | S | Weighted decimation keeps vertices at shoulders, elbows, wrists, hips, knees, neck. (Instant Meshes: rejected for clothed meshes — fuses layered cloth; **reconsider for the base body**, which is a single closed form.) |
| 1.9 | **De-light the base colour** | M | Generator painted shading/highlights into albedo; flatten so game lighting isn't doubled. Applies to body and garment bakes. |
| 1.10 | Sculpt / art leftovers | M | Male toe/sole shape and female heels (now garment fixes: boots), female plume as alpha feather cards (hat garment). |

**Exit:** base goose body (A-pose, symmetric, scaled from the male, eye asset, split beak), ≤20k tris, validator-clean.

## M2 — Standard goose rig

| # | Item | Size | Notes |
|---|---|---|---|
| 2.1 | **New standard rig** | M | **D3 decided:** new rig (not the Track 1 bike-monolith rig or Track 2's 24 bones). Humanoid deform skeleton with conventional names (retargetable, Mixamo-style) + goose extras: 3–4 bone neck, head, upper/lower beak, eye L/R, lids, tail feathers, hat socket, coat-tail and skirt chains. Built on the base body. |
| 2.2 | **Fit to the base body** | S | One skeleton, one set of bone positions (both geese share the body). |
| 2.3 | **Skinning the base body** | L | Auto weights + cleanup, mirrored; Track 1 lessons: check every vertex's displacement, avoid partial-weight leakage. |
| 2.4 | **Test animation set** | M | Idle, blink, look-at, honk, wave, sit — proves the rig before garments. |
| 2.5 | Export + three.js check | S | Skinned GLB loads in the game's loader, clips play, size sane. |

## M4 — Wardrobe and colour changes

The past attempt to *generate* separate garments with TRELLIS was rejected ("garbage and slop":
melted geometry, shadows painted in, clipping). This plan keeps the current *look* and changes
only the *structure*.

| # | Item | Size | Notes |
|---|---|---|---|
| 4.2 | **Garment shells from the v4 look** | L | Per garment (male: coat, waistcoat, shirt/collar, bow tie, breeches, boots, gloves, bowler; female: dress, hat + plume, brooch, gloves, boots): clean shell over the base body (shrinkwrap/solidify/retopo) pushed out to the v4 silhouette, texture **baked from the v4 hi mesh**. v3 region groups are the starting map. |
| 4.3 | **Outfit system** | M | Garments skinned by weight transfer from the body + painted fixes (**D4 decided:** limited motion → bone chains + careful weight painting for coat tails and skirt, no cloth sim; goal is no mesh breaking). Per-outfit body-hiding masks so nothing pokes through; show/hide swap in the game. |
| 4.6 | **Colour changes** | M | Recolourable garments: bake each garment's colour as detail (luminance) + tint mask, tint at runtime in three.js (like the bike chooser's recolourable frame). Palette presets per outfit. |
| 4.4 | **Second outfit** | M | Proves the system: e.g. swap pieces between the two geese, or a cycling outfit. |
| 4.5 | Riding check | M | Every outfit in the M3 seated/pedalling poses without breaking. |

## M3 — Riding the tandem

| # | Item | Size | Notes |
|---|---|---|---|
| 3.1 | **Bike model** | L | Same pipeline from `refs/bicycle-turnaround.png` (PLAN §9), or decimate Track 2's 59k rigid bike. Rigid parts as separate nodes (wheels, cranks, pedals, chain, bars). Sets the absolute game scale. |
| 3.2 | **Seated riding pose** | M | From the M2 rig: hips on saddles, hands on grips, feet on pedals (captain front, stoker rear). |
| 3.3 | **Skirt + coat-tail weighting for riding** | M | **D4 decided:** bone chains + weight painting (see 4.3); verify the seated/pedalling range. |
| 3.4 | **Pedal + lean animation** | M | Crank-driven leg IK (legs 180° out of phase), torso/head lean per rider (captain and stoker lean independently, as in the game today). |
| 3.5 | **Game integration** | M | Replace the fused Track 1 riders behind *Show Riders*; outfits + colours selectable; versus mode clones (SkeletonUtils). |

## M5 — Game delivery

| # | Item | Size | Notes |
|---|---|---|---|
| 5.1 | **Size budget** | S | GLBs are ~13 MB with 2048 PNGs; ship KTX2 or WebP + Draco/meshopt (Track 1 went 62 → 3.3 MB). |
| 5.2 | LODs | S | Distance LODs for versus mode (several bikes on screen). |
| 5.3 | Perf check | S | Body + outfit + bike per rig, N rigs in versus, on the target laptop + web. |

## Decisions

| | Decision | Outcome (Pete, 2026-10-10) |
|---|---|---|
| D1 | Scale reference | **The male.** Base body inherits his scale; game height set with the bike. |
| D2 | Eye look | **From the reference sheet:** oval opening, eyelids, colours. Standalone review before integrating. |
| D3 | Rig | **New standard rig** (not Track 1 / Track 2). |
| D4 | Skirt / coat tails when riding | **Limited motion:** bone chains + weight painting so the mesh never breaks; no cloth sim. |
| D5 | Wardrobe vs riding first | **Wardrobe and colour changes first**, then riding in the game. |
| D6 | One shared base body for both geese | *Proposed* (follows from D1–D3) — Pete to confirm. |

## Risks

- **Base body (1.0) is new ground** — nothing in the current meshes shows what's under the coat or dress. Mitigation: evaluate the July mannequin first; keep the v4 head/neck which already match the sheet.
- **Generated-mesh quality ceiling** — double-walled shells, painted lighting, fused layers. Mitigation: generated meshes are *look reference + bake source* only; clean structure is built underneath.
- **12 GB laptop GPU** — generation at the 1024 tier needs Antigravity's ComfyUI and Pete's Blender closed (see PLAN.md).
- **Scope** — the wardrobe (M4) now precedes riding; the fused Track 1 riders stay in the game meanwhile.
