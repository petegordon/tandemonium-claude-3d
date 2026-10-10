# Tandemonium geese — roadmap

Where the Victorian Canada-goose characters go after v3, and how the pieces depend on each
other. `PLAN.md` is the pipeline manual and progress log; this file is the plan of record.
Each numbered item below is a GitHub issue; each milestone is a GitHub milestone.

## Where we are (v3, 2026-10-10)

- Male (seed 42) and female (seed 123) generated with Pixal3D multi-view from
  `refs/characters-turnaround.png`, cleaned by fix plugins, remeshed + baked to **one skinned-ready
  mesh each: 19,558 tris, 1 draw call, glTF validator 0/0**, A-pose. Pete: "look really good".
- Repeatable pipeline: `comfy_job.py` → `clean_hi.py` → `retopo_bake.py`, per-character config in
  `chars/<char>.json`, fix plugins in `scripts/fixes/`.
- Already in the game (separate, older line — "Track 1"): one fused 500k-tri bike + both riders,
  39-bone lean rig, behind the *Show Riders* option. A modular "Track 2" discovery (bike + goose +
  show/hide garments on a 24-bone rig) lives in `BlenderMagic/`. Lessons from both are folded in below.

## The three goals and why they pull on each other

1. **Ride the tandem** — both geese seated, pedalling, leaning; in the game.
2. **Reuse** — one goose "species": same skeleton, eyes, beak, feet, head proportions, palette,
   animations on male and female (and any future goose).
3. **Change clothes** — outfits as separate meshes swapped at runtime.

They share one foundation: a **clean, symmetric, correctly-scaled base character with a shared
rig**. Riding needs it (pedal IK, lean), reuse *is* it, and clothing needs a body underneath
it to fit garments onto. So the order is foundation first, then riding (the game needs it
soonest), then the wardrobe.

```
M1 Foundation ──► M2 Shared rig ──► M3 Riding the tandem ──► M5 Game delivery
      │                 │                    ▲
      └────────────► M4 Wardrobe ────────────┘   (outfits reuse the M2 rig;
                                                   riding outfits need M3's seated pose)
```

## M1 — Foundation (v4 A-pose geese)

Fix the base geometry everything else inherits. Every change is a pipeline step or plugin, so both
geese (and the bike later) re-run from config.

| # | Item | Size | Notes |
|---|---|---|---|
| 1.1 | **Scale by body landmark, not hat top** | S | Both are 1.8 m *including hats*, so the female's body is shrunk by her tall plume (eye height 1.555 vs 1.61 m; eye spacing 10.6 vs 14.6 cm). Measure a landmark (eye or shoulder height) on `refs/assembly-turnaround.png` / `source-reference.jpg`, scale both from it. Settles game height together with the bike. |
| 1.2 | **Straighten the head** | M | Heads are yawed toward −X (male ~15°, female ~38°, as drawn). New hi plugin `head_straighten`: angle from the eye-pair axis, neck pivot, smooth falloff down the neck so collar/shoulders stay, hat turns with the head. Check the female's neck twist for stretching. |
| 1.3 | **Symmetry audit** | S | Measure L/R arm, shoulder, torso asymmetry after 1.2; fix gross offsets (mirrored weights depend on it). |
| 1.4 | **Shared species palette + proportions** | M | Two generator runs gave different feather black / cheek cream / beak grey and head/beak shapes. One palette (recolour plugin pass) + compare head/beak proportions after 1.1. |
| 1.5 | **Reusable eye asset (eyeball + lids)** | M | Replaces v3's "circles in circles". Script-built asset: eyeball (sclera/iris/pupil texture + glossy cornea), upper/lower lid shell that forms the sheet's almond opening, catchlight card fixed to the lids, eye bone + blink controls. Own small shared material (+1 draw call). Pete approves a standalone close-up vs the sheet **before** it goes on the heads. |
| 1.6 | **Split the lower beak** | S | Separate lower mandible region + hinge so honk/quack is possible. Cheap now, painful after skinning. |
| 1.7 | **Armpit / glove fusion check** | S | Voxel remesh fuses near-touching parts; verify arms and gloves are free of coat/dress so skinning won't tear. |
| 1.8 | **Joint density** | S | Weighted decimation keeps more vertices at shoulders, elbows, wrists, hips, knees, neck (budget unchanged). Instant Meshes was tried and rejected for the full mesh (fuses layered cloth). |
| 1.9 | **De-light the base colour** | M | Generator painted shading/highlights into albedo; flatten so game lighting isn't doubled. |
| 1.10 | Sculpt / art leftovers | M | M3 male toe/sole shape, F4 heels, F2 plume as alpha feather cards, female faint lash marks. |

**Exit:** v4 male + female A-pose GLBs, symmetric, scaled, shared eyes, validator-clean, ≤20k tris.

## M2 — Shared goose rig

| # | Item | Size | Notes |
|---|---|---|---|
| 2.1 | **Rig standard decision** | S | Reuse Track 2's 24-bone rig, or a new humanoid set with conventional names (retargetable mocap/Mixamo-style). Add: eye L/R, lids, lower beak, skirt/coat-tail chains, hat. Pete decides. |
| 2.2 | **One skeleton fitted to both geese** | M | Same bone names/hierarchy; per-character bone positions from landmarks. |
| 2.3 | **Skinning** | L | Auto weights + cleanup; mirrored from the symmetric base; lessons from Track 1: lock rigid parts by colour+zone, check every vertex's displacement (not samples), avoid partial-weight leakage. |
| 2.4 | **Test animation set** | M | Idle, blink, look-at, honk, wave — identical clips play on both geese (proves reuse). |
| 2.5 | Export + three.js check | S | Skinned GLB loads in the game's loader, clips play, size sane. |

## M3 — Riding the tandem

| # | Item | Size | Notes |
|---|---|---|---|
| 3.1 | **Bike model** | L | Same pipeline from `refs/bicycle-turnaround.png` (PLAN §9), or decimate Track 2's 59k rigid bike. Rigid parts: wheels, cranks, pedals, chain, bars as separate nodes for animation. Fixes the game scale with 1.1. |
| 3.2 | **Seated riding pose** | M | Pose library from the M2 rig: hips on saddles, hands on grips, feet on pedals (captain front, stoker rear). |
| 3.3 | **Skirt + coat-tail decision** | M | The female's bell skirt has no legs inside and the male's coat tails are fused to the breeches — pedalling legs will tear them. Options: (a) skirt/tail bone chains following the thighs loosely, (b) model riding garments in the seated pose, (c) pull M4's separate garments forward for these two pieces. Pete decides. |
| 3.4 | **Pedal + lean animation** | M | Crank-driven leg IK (legs 180° out of phase), torso/head lean per rider (the in-game Track 1 behaviour: captain and stoker lean independently). |
| 3.5 | **Game integration** | M | Replace the fused Track 1 riders behind *Show Riders*; captain/stoker clips; versus mode clones (SkeletonUtils). |

## M4 — Wardrobe (clothing changes)

The past attempt to *generate* separate garments with TRELLIS was rejected ("garbage and slop":
melted geometry, shadows painted in, clipping). This plan keeps the current *look* and changes
only the *structure*.

| # | Item | Size | Notes |
|---|---|---|---|
| 4.1 | **Base goose body** | L | An undressed body with the M2 rig: feathers, neck, head/eyes/beak, feet, limbs. Sources: sculpt down from the v4 meshes, or reuse the existing `goose_naked` mannequin. Male/female as one body + shape keys if proportions allow. |
| 4.2 | **Garment shells from the v4 look** | L | Per garment (coat, waistcoat, shirt/collar, bow tie, breeches, boots, gloves, hat; dress, hat, brooch): clean shell built over the base body (shrinkwrap/solidify/retopo) and pushed out to the v4 silhouette, then **bake its texture from the v4 hi mesh** — keeps today's look with clean topology. The v3 region groups are the starting map. |
| 4.3 | **Outfit system** | M | Garments skinned to the same rig (weight transfer from the body); per-outfit body-hiding masks so nothing pokes through; show/hide swap in the game. |
| 4.4 | **Second outfit** | M | Proves the system: e.g. cycling outfit, or swap pieces between geese. |
| 4.5 | Riding versions | M | Outfits checked in the M3 seated pose (skirt solution from 3.3). |

## M5 — Game delivery

| # | Item | Size | Notes |
|---|---|---|---|
| 5.1 | **Size budget** | S | GLBs are ~13 MB with 2048 PNGs; ship KTX2 or WebP + Draco/meshopt (Track 1 went 62 → 3.3 MB). |
| 5.2 | LODs | S | Distance LODs for versus mode (several bikes on screen). |
| 5.3 | Perf check | S | 2 riders + bike per rig, N rigs in versus, on the target laptop + web. |

## Decisions Pete owns

| | Decision | When |
|---|---|---|
| D1 | Scale landmark + game height (with the bike) | M1.1 |
| D2 | Eye asset look (standalone review) | M1.5 |
| D3 | Rig standard: Track 2 24-bone vs new humanoid naming | M2.1 |
| D4 | Skirt / coat-tail solution for riding | M3.3 |
| D5 | Wardrobe before or after riding in the game | after M2 |

## Risks

- **Generated-mesh quality ceiling** — double-walled shells, painted lighting, fused layers. Mitigation: treat the generated mesh as *look reference + bake source*, build clean structure underneath (M4).
- **12 GB laptop GPU** — generation at the 1024 tier needs Antigravity's ComfyUI and Pete's Blender closed (see PLAN.md).
- **Scope** — M4 is the largest block; M1–M3 deliver riding geese without it.
