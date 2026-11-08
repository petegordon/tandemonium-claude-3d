# Garment body: no tail under the clothes (2026-11-07)

Pete: "That tail on the base image really costs time in these outfits; we need a permanent foundational fix: hide the
tail entirely when dressed and have the back of the dressed geese look more human-like where the tail is."

![](img/garment_body.jpg)
(Side view: left = garment body, right = base goose. Rear view: left = base, right = garment body.)

## What it is
`scripts/make_garment_body.py` writes `out/base-goose/garment_body.npz`: the base goose's game mesh, same vertices in
the same order (bones, weights and every per-vertex table still match), with the back of the hips reshaped:
1. each 1 cm height band through the hips is filled out to its convex hull at the back (cloth spans the hollow under
   the tail root instead of caving into it);
2. the tail's vertices (dominant bone = Tail, the same rule the dresser hides by) are pressed onto that surface;
3. two rounded cheeks are added, the zone relaxed, and nothing but the tail ever ends up inside the real body.

```
blender -b --factory-startup --python scripts/make_garment_body.py -- --relax 30 [--render]
```

## Where it is used
- `make_garment.py` builds every garment on it (chars json `"garment_body": false` opts out). Every outfit built
  before 2026-11-07 was tuned on the real rump and has `"garment_body": false` set (outfit_male, outfit_female,
  both cyclists, both Victorians, both Georgians, grandma, grandpa): their per-outfit `seat_shape` settings would
  double up if rebuilt on the garment body as they are. Rebuilding one on it = drop the flag, drop/retune
  `seat_shape`, rebuild, review (Tandemonium #635).
- `make_robot_parts.py` (robot outfit, branch `feat/robot-outfit`) fits its parts to it.
- `dress_goose.py`:
  - matches a garment's covered-vertex list on the real body as always (`make_garment.py` writes the covers of a
    garment-body garment at the real rump positions: `base_goose.blend`'s vertex order differs from the rigged
    glb's, so the first version's index-based match of the npz positions left rump specks showing, 2026-11-08);
  - hides the tail plus **7** rings of rump faces round it (was 2) under breeches, coats and dresses
    (`"tail_rings"` per character).

  Both only when the outfit is on the garment body: with `"garment_body": false` the dresser behaves exactly as
  before (covers matched on the real rump, 2 tail rings).

  So in the game the real tail is never drawn under the clothes, and the clothes' seat is a person's seat.
- `tools/threejs_check/prop_check.mjs` hides `<piece>__<a+b>` sub-meshes like the game, so game-lit reviews no longer
  show the tail and feet that are hidden in the game.

## First outfit on it
The robot outfit (`docs/robot-outfit.md`): no seat_shape hacks, no tail poking through.

## Fixes found on the first older-outfit rebuild (cyclist gent, 2026-11-08)
- `make_garment_body.py` relaxed over the glTF mesh's split UV seams, so seam duplicates drifted apart and opened cracks
  through the seat once `make_garment.py` welded the body (breeches region in fragments, crumpled seat, breeches and
  shirt through the vest's hem). The relax now runs on the welded mesh (PR #45).
- Covers are written on the real rump (above).
- Review renders: `outfit_beauty.py --pose riding` (a `rig_poses.Poser` pose instead of the first clip) for seated
  close-ups of the seat.


## Georgian gent (2026-11-08)
`outfit_male_georgian`: `garment_body` flag and the breeches `seat_shape` (bulge 0.022) dropped; breeches, shirt,
waistcoat and the frock coat + coatskirt (`build_georgian_coat.sh`) rebuilt, `dress_goose --tag full --variant withshoes`.
`force_hide` (Tail under breeches + coatskirt) kept: harmless next to the 7 tail rings. The coatskirt no longer caves
into the hollow under the tail root; in the game the skirt covers the seat, so riders look nearly the same. The
coatskirt chain bones re-fit to the new skirt, so riders, Pedal_PF and show clips ship together.

## Grandpa (2026-11-08): the garment body on a slider-shaped body
`outfit_grandpa` (slider body, garments built on the shaped body, no `shells_on_base`): `garment_body` flag dropped,
breeches `seat_shape` bulge 0.02 -> 0 (the cleft and fold were already 0; the seat `fill` + `relax` stay: they smooth
the shaped seat), breeches, shirt, waistcoat and cardigan rebuilt (`CHAR=outfit_grandpa build_cyclist.sh`, trims
included), `dress_goose --tag full`. Sheet: `img/garment_body/grandpa_contact_sheet.jpg`.
Two `make_garment.py` fixes, both only for a garment-body garment on a slider body:
- the real-rump cover positions get the same slider shape as the body (PR #47); without it the masks missed
  everywhere the sliders move vertices (body through the trousers, cardigan, ankles);
- the garment body's moved vertices take their slider shape from Hips instead of Tail (the pressed-in tail is seat
  now). On the Tail bone they moved apart from the seat round them, so the seat came out lumpy and folded.
