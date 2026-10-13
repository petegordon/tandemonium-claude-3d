# Victorian outfit: the garment loop (2026-10-12, Pete: iterate every garment to a high design + finish standard)

Goal: every garment complete (no holes, every button / trim / pattern), placed right on the naked base goose, beautiful;
several versions per garment, several full-body geese per garment, and three full outfits on the base goose:
1) all garments, 2) all but the jacket, 3) all but the jacket and the vest.

## Principle
- **Geometry from the body, appearance from Pete's drawings.** Shapes are built on the base goose by the parametric
  builders (make_garment / make_hat / make_accessory): clean, fitted, layered, riggable. The look -- brocade, gold
  trim, brass buttons, collars, cuffs -- is PROJECTED from Pete's drawings, which the part-to-part warp already puts on
  our body in four calibrated views. So the pattern and every button come from the drawing itself.
- **Measured, then scored.** Every version is rendered on the base goose from the same four calibrated cameras as the
  references and compared with them (silhouette IoU per view, colour error inside, hole check), then reviewed by
  independent reviewer agents with a fixed rubric (completeness, placement, finish, beauty). The best version wins.

## Per garment, per iteration
1. **Reference** (`ref_dress.py`): SAM garment mask on each drawing view (per-view prompts from our landmarks through
   the part warp), holes filled (buttons are separate objects to SAM), warped onto the blue mannequin; saved as
   RGBA (alpha = garment) in front / left / rear / right. Check: no holes, the whole garment present in every view.
2. **Measure** (`key_measure.py`): edges, coverage and ease on our body.
3. **Build** (`make_garment.py` and friends): recipe from the measurements; 2-3 variants where a parameter is uncertain.
4. **Texture** (`project_bake.py`): bake the four reference views onto the garment's UVs (each texel from the views
   that see it: facing weight x visibility x the reference's garment alpha); texels no view covers are filled from
   their neighbours. Buttons / studs that stand proud get modelled brass geometry.
5. **Score** (`garment_score.py`): render the garment on the base goose in the four calibrated views; silhouette IoU
   vs the reference garment mask, mean colour error inside, holes; side-by-side sheet.
6. **Review**: reviewer agents (fresh eyes) grade the sheet against the drawings; list concrete defects.
7. **Iterate**: fix the defects (recipe / code), next version. Stop when every view scores well and the reviewers find
   no blocking defect.

## Outfits
`dress_goose.py` layers and skins the chosen shells (masks hide the body under them, tail hidden under breeches and
jacket); beauty renders front / side / rear / 3-4 on the naked base goose for each of the three outfits.

## Round 3 (2026-10-13): plume, jacket, bow tie, lighting, shirt
- **Plume** (`make_hat.py` `hat_design.plume.feathers`): three alpha-cut feathers (procedural texture: rachis,
  slanted barbs in clumps, ragged ends and splits, downy base, brown -> gold) on curved, twisted, V-folded strips fanning
  from a rimmed, domed brass medallion on the band (`angle_deg` from the front, `face_front` so they read from the front).
- **Jacket**: the dark shoulder-blade marks were three stacked faults, found one by one with clay / flat-colour /
  object-ID / back-face renders --
  1. `make_garment.py` coat/vest clearance: rays from the back by the armpit hit the shirt *sleeve* and pushed the coat
     out 8 cm into shards -> a hit counts only on a roughly parallel layer (`under_cos`, default 0.5);
  2. the sleeve and back sheets crossing in the armpit -> `relax_folds.py` (Taubin relax of flipped faces and of
     `--spheres` regions, kept clear of the body; `--over ""` -- pushing out onto the lumpy shirt re-crumpled it;
     dress_goose's layer masks hide what the coat covers anyway);
  3. the coat's normal map still carried the old crumples -> `clean_normal.py` flattens texels tilted > 25 deg
     (run on coat, shirt, vest, breeches).
  Plus: `project_bake.py` pads the UV islands (push-pull) before saving, `--lift` swaps broad painted shadows for the
  fabric tile, `--speck` refills near-black specks; `add_buttons.py` skips blobs seen through an opening (hit facing
  away). Stray brass dots at the breeches' crotch / inner thighs removed.
- **Bow tie** (`make_accessory.py`, `accessory_design.bowtie.bow_texture`): butterfly wings + wrapped knot, front-
  projected from the 4x product shot (`prep_bow_texture.py` crops it and grows the colours over the grey backdrop); the
  bow keeps its own UVs through the smart-project. Neck band dropped, collar gap 1.5 deg, collar 6 mm off the neck.
- **Lighting** (`outfit_beauty.py`): seamless cyclorama turning with each view (no horizon, no blown-out floor), floor
  0.16 grey, key 450, a low kicker, exposure -0.6, rough non-metal materials' specular 0.2 (`--cloth-spec`; the default
  0.5 laid a white film over the burgundy: rendered (148,85,87) vs the drawing's (89,35,39)).
- **Shirt**: bishop sleeves (`ease.puff` 0.05 at 1.55 upper-arm lengths, width 0.45; cuff 6 cm). Under the jacket the
  slim-sleeved shirt is used: `dress_goose.py --variant jacket` takes shells/variants/jacket/* over shells/*. Tucked
  in: `tuck.push_in` moves shirt vertices with the breeches just behind them inside the breeches (clean waistline
  instead of a sawtooth of hidden faces); tuck line z_top 0.968, rise 0.67, margin 0.03.

Outfits: `--tag full --variant jacket`, `--tag nojacket --variant vest --without coat`, `--tag shirtonly --without coat,waistcoat`.

## Round 4 (2026-10-13): reviewer's round-3 defects
- **Jacket hem** was sawtoothed by the late body shape: a tail vertex weighted mostly to its cloth chain kept a
  sliver of leg weight, renormalised into noise. `dress_goose.py` now smooths each garment's late-shape displacement
  over the mesh (`--late-smooth`, 30 passes; body-weighted vertices hold their own move more).
- **Jacket tails** to the knee (`outline.z_back` 0.45), **gold piping** on every open edge (`add_piping.py`: boundary
  edges found by position, since the glTF stays split along UV seams), **brown lining** (`add_lining.py`: inset,
  flipped copy of the cloth). Built over the SLIM shirt (`shells/variants/jacket/shirt.glb`), not the bishop one.
  **12 front buttons** in 2 x 3 per panel at the drawing's spots (`add_buttons.py --extra-only --extra-ray`).
- **Gloves**: the base goose's hand is a fused mitt, as in Pete's worn reference -- no fingers invented. The cuff is
  what reads: taller (5 cm), flared, cream (it rendered white), button 12 mm turned to the front
  (`make_glove_cuff.py --button-r --button-front`); leather left plain (the bake put a tan tip on it).
- **Breeches**: level waistband (`back_rise` 0, as the drawing), fabric tile only (no painted blobs / crotch shadow),
  12 modelled gold buttons (2 x 3 by each side seam, front and back) + the knee pair. Shirt tuck line follows (rise 0).
- **Boots**: the calf poked through the shaft's back -> every body vertex below the boot rim is hidden.
- Vest back stays brocade (Pete's rear reference has it); the pale flap was the old glove cuff, gone.
- Hat medallion larger (21 mm) and turned toward the front.

## Round 5 (2026-10-13): doubled jacket buttons, mottled cloth, shirt collar + pin-tucks
- **Painted buttons erased from the references** before baking (`erase_ref_buttons.py --zone xmin,xmax,zmin,zmax`:
  the button panel in body metres, projected through the calibrated cameras; inside it every round gold blob -- even
  one touching the edge trim, by its round core -- is filled from the cloth around it; originals kept as *.orig.png).
  The modelled brass buttons are then the only buttons.
- **Clean burgundy**: `project_bake.py --flatten 0.9` evens the cloth's broad light / dark blotches toward its median
  colour (gold = yellow texels kept), and `--cloth-tile 12` puts the fabric weave in the median burgundy on plain cloth
  more than ~12 texels from any gold -- the drawing's embroidery, lapels and cuffs stay, the painted wear goes.
- **Shirt collar**: taller standing collar (`collar_h_scale` 1.35), bow lower on it (`bow_z_frac` 0.12), wing tips,
  two gold collar studs (`collar_studs`). **Pin-tucks**: `add_pleats.py` -- 4 raised half-tube tucks each side of the
  placket, ray-snapped to the shirt, in the shirt's cloth.
- **Waist**: breeches' top cut straight (`trim_edge.py --z 0.936 --rise 0.13 --y0 -0.15`, recorded as
  `breeches.trim_top`), shirt tuck line matches; the shirt rebuilt denser (7000 tris) -- its big triangles spanned the
  band and cut through it; the tuck push skips vertices already inside the outer garment and eases its depth in from
  the rim (`push_ramp`, `push_reach`, `push_above`).

## Round 6 (2026-10-13): reviewer's round-5 defects
- **Breeches**: gold buttons on the FRONT only (2 x 3 by the fall) + the outer knee pair (Pete); recorded in
  `garment_design.breeches.buttons`.
- **Jacket** (whole chain in `scripts/build_victorian_coat.sh <tag>`):
  - standing **collar** at the back with gold piping (`add_collar.py`: from the coat's neckline boundary);
  - **cuffs**: modelled turn-back bands at the sleeve ends wrapped in the drawing's cuff brocade (`add_coat_cuffs.py`,
    `cuff_texture.png` = mirrored crop of the drawn cuff), gold piping on top, burgundy rim; they clear the glove
    gauntlets (`--over gloves`); the drawn cuff is kept out of the projection (`project_bake.py --tile-near`: spheres
    where no view projects and the fabric tile fills -- also used for the plain sleeves and the hip sides);
  - **lapels** painted at texel resolution (`project_bake.py --lapel z0,z1,w,w_top,front_y,scale,texture`): the
    drawn lapel brocade, tiled, inside a width field from the open front edge, a gold edge line, a plain-cloth halo
    outside it (the drawing's lapel had landed on the shoulder); a mesh cut (`add_lapels.py`) was too jagged at this
    density -- kept as a tool, not used;
  - gold **flecks** (`--speck-gold`): an opening of the gold mask keeps real trim, the specks become cloth;
  - **wool**: weave tile 3 cm (was 6: read as quilting), normal-map mottle 0.05 (was 0.2), normals flattened > 12 deg;
    slimmer ease (torso / sleeve 0.016), tails z_back 0.40, relaxed clear of shirt AND vest (`--over shirt,waistcoat`).
- **Gloves**: the gauntlet cuff goes over the shirt cuff (`make_glove_cuff.py --over shirt,variants/jacket/shirt`),
  reaching toward the hand (`--below 0.05`), warm cream, gold button low on it (`--button-at`).
- **Shirt** pin-tucks bolder (r 3.8 mm, 14 mm apart).
- **Seated pose**: front skirt chains follow the thighs fully, sides 0.85 (`FOLLOW`, `DRAPE_BY` in dress_goose.py).
  STILL OPEN: the breeches' thigh-back swells through the coat's side-back panel and the tails stay vertical when
  seated -- needs its own round (tails resting on the saddle, back chains following, or a pose-aware layer mask).
- **Shirt variants**: `shells/variants/jacket/` (slim sleeves, under the coat) and `shells/variants/vest/` (pin-tucks
  only where the vest leaves the shirt visible: `add_pleats.py --clear-of waistcoat` -- they poked through the vest).
  Outfits: `--tag full --variant jacket`, `--tag nojacket --variant vest --without coat`, `--tag shirtonly --without coat,waistcoat`.

## Round 7 (2026-10-13, final): riding pose, back vent + tab, front buttons, lapels
- **Riding / seated**: the coat's skirt over the breeches takes the breeches' FINAL skin weights (`FOLLOW_INNER` in
  dress_goose.py, breeches skinned first via `LAYER_RANK`): within 6 cm full, fading to 12 cm, all round, up to 12 cm
  above the hip joint, the blend's edge smoothed 14 rings. The thigh no longer comes through the skirt; far tail tips
  keep their hanging chains. (Front chains follow 1.0 / sides 0.85 from round 6 still apply to what is left.)
- **Back**: vent narrowed (`outline.tails` z_top 0.70, w_bot 0.03, pow 2.0); half-belt tab with gold piping and two
  domed buttons (`add_back_tab.py`).
- **Front**: buttons 17 mm, two columns of three nearer the opening; lapels wider (`--lapel` w 0.035 -> 0.10).
- Chain: `bash scripts/build_victorian_coat.sh <tag>`; outfits as in round 6.
