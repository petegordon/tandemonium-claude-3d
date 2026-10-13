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
