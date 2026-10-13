# 1920s cyclist outfit (male), from text-to-image references (2026-10-13)

Pete: "Let's do the full pipeline with all the iterations and judging and take it all the way to completion at high
quality yourself." The source is the approved text-to-image set ([t2i-reference-views.md](t2i-reference-views.md)):
- flat cap, white shirt with a green knitted tie;
- argyle V-neck sweater vest;
- herringbone plus-fours with buckled knee straps;
- green knee socks, brown wingtip brogues, tan driving gloves.

Result: `out/outfit_male_cyclist-goose/outfit_male_cyclist_full_dressed.glb`. It is rigged and skinned like the
Victorian outfit, the leg slider is applied, and it carries all the clips. It passes the glTF validator with 0 errors
and renders in three.js r161 in every pose. Sheets are in `docs/img/cyclist/`.

## Method
1. **Calibrated references.** The approved views were 50 mm beauty shots. They are re-staged onto the naked goose
   (tail removed) in the four orthographic key cameras (`refs/key_views/cameras.json`). Picture 1 is the naked key
   view; picture 2 is the approved front. Results are in `refs/outfit_male_cyclist/t2i/key1/`:
   ```
   blender ... outfit_beauty.py -- --glb out/base-goose/base_goose_rigged.glb --out renders/t2i/key_notail.png \
       --floor 0.6 --views front:0,left:90,rear:180,right:-90 --hide-bones Tail --cams refs/key_views/cameras.json
   python scripts/t2i_outfit.py --outfit outfit_male_cyclist --seed 21 --views front,left,rear \
       --base "renders/t2i/_key_notail_{view}.png" --tag key1 --front refs/outfit_male_cyclist/t2i/pick/front.png --restage
   ```
   The image model re-proportions the body (narrower shoulders, longer thighs), so its pixels are not projected
   onto our body. Heights and widths were read off the views against a metric ruler and set in the recipe against
   our joints. The reviewers compared every version with these views from the same cameras (`review_pack.py`).
2. **Geometry from the body (existing builders and three new ones), appearance procedural.** The recipe is
   `chars/outfit_male_cyclist.json`, and `bash scripts/build_cyclist.sh [pieces]` builds each piece in order:
   - **breeches** (plus-fours): `make_garment.py` kind breeches.
     - New `ease_z` (ease by height: snug hips, full at the knee).
     - New `knee_ramp` (the blouse drops sharply to the knee band).
     - New `outer_smooth` (Taubin smoothing of the offset surface, so loose cloth bridges the feather bumps and the
       tail-cap rim).
     - Then `add_kneestrap.py`: buckled leather straps joined into the shell as their own materials.
   - **shirt**: kind shirt, slim sleeves, tucked into the plus-fours.
   - **waistcoat** (sweater vest): kind vest with new `knit` (ribbed hem, V and armhole bands in the normal map; no
     lapels, buttons, pockets or strap) and new `outline.arm_oval` (a clean scooped armhole: an oval in the side view
     plus the arm-weight iso line). It is built over the shirt, breeches and necktie.
   - **gloves**: kind glove with `round` (blunt mitt tips).
   - **socks**: kind boot. `shells/socks.glb` keeps the whole foot, for wearing alone. `shells/variants/withshoes/socks.glb` is trimmed below 7.5 cm inside the shoe; the webbed foot is wider than the shoe and poked out of it.
   - **boots** (brogues): `make_boot.py` with a low top line. New `sole_smooth` / `sole_step` replace the toothed
     voxel sole.
   - **hat** (flat cap): new `make_cap.py`.
     - A crown lofted from a head band ray-fitted to the head, with a flat superellipse top pulled forward.
     - Its front edge snaps down onto a stiff crescent peak, and there is a covered button.
     - A clearance pass on the subdivided crown keeps it off the head; the bill's ridge had poked between its
       vertices.
   - **necktie**: new `make_accessory.py --piece necktie`.
     - A turned-down collar (stand plus a fall with points that lies over the vest).
     - A four-in-hand knot in the collar opening.
     - A knitted blade lying on the shirt.
   - **Every piece** then goes through `clean_normal.py` (`normal_tilt` per piece) and `pattern_paint.py`.
3. **Patterns in 3D** (`pattern_paint.py`, recipe "patterns"). Each texel's surface point and normal are rasterised
   from the garment's own UVs, so the pattern follows the body, not the UV islands:
   - herringbone tweed: columns by arc length round the body at a fixed radius `r0`, slubs and flecks;
   - argyle: knitted round the body, a cream centre diamond on the chest, an overcheck, a stockinette shade, plain
     mustard knit back;
   - ribbed bands along the garment's open edges;
   - ribbed socks, and a horizontal knit rib for the tie;
   - brogue: wingtip W seam with punched holes, toe medallion, quarter and heel seams, laces, eyelets, burnished
     toe and heel;
   - driving glove: wrist strap with stud, three points, perforated knuckles.

   The make_garment detail bake is kept as shading (`detail_gamma`); the colour factor goes white.
4. **Dressing**: `dress_goose.py --char outfit_male_cyclist --tag full --variant withshoes`, with new per-character keys:
   - `layer_ignore`: the plus-fours' knee band is never hidden by the socks or shoes (that mask tore the hem into a
     sawtooth);
   - `skin_merge`: the vest's hem gives its leg weights to the hips, so it stays flat when seated.
5. **Judging**: `bash scripts/review_cyclist.sh <tag>` renders the reference-vs-ours sheet, the beauty sheet and
   close-ups. Independent reviewer agents graded each round with a fixed rubric (completeness, placement, finish,
   fidelity). Rounds v1 → v5:
   - the trouser silhouette moved from wide hips to volume at the knee;
   - the hem sawtooth, the head poking through the cap, and the gap between crown and peak were fixed;
   - the gloves went from reading as skin to leather with detailing;
   - the vest back's blotches (2 cm colour noise) were removed;
   - the vest is flat when seated;
   - the shoe toe, sole, and the collar round the ankle were fixed;
   - the tie was pressed onto the chest, with the knot between the collar points.

## Limits / next
- The hands are the base goose's mitts (D8): the gloves follow that shape. The reference shows fingers.
- The straps sit at the knee band. The reference has the blouse drooping over them, which would need folded cloth
  geometry.
- Other outfits: write `refs/<outfit>/t2i_prompt.json`, re-stage it in the key cameras, add a recipe, and run
  `build_cyclist.sh` with `C=` changed. (A general per-outfit runner is still on the list.)

## Round 7 (Pete): hat too low, seat not right, garments usable one at a time
- **Cap:** the head band went up 2.2 cm (`band_z` 1.632), so the peak sits above the eyes.
- **Seat:** the plus-fours' seat read as one flat panel with the legs splitting low.
  - `outer_keep_gap` keeps the outer smoothing off the crotch.
  - `seat_shape` adds a centre cleft and a fold under each cheek.
  - `patterns.breeches.back_seam` paints a centre back seam.
- **One garment at a time:** `bash scripts/dress_singles.sh` puts each garment alone on the naked base goose, rigged
  and skinned with all the clips: `out/outfit_male_cyclist-goose/outfit_male_cyclist_only_<piece>_dressed.glb`
  (hat, necktie, shirt, waistcoat, gloves, breeches, socks, boots). All of them, and the full outfit, pass the glTF
  validator with 0 errors and 0 warnings. Sheet: `docs/img/cyclist/cyclist_garments_single.png`.
- **Unrigged pieces:** the bare garment shells are `shells/<piece>.glb`. Each has `<piece>_weights.npz`, the base
  body's skin weights per vertex, which dress_goose uses.
