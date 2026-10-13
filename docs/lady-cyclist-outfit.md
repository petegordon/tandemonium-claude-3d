# 1920s lady cyclist (female goose), from text-to-image references (2026-10-13)

This is the partner to [cyclist-outfit.md](cyclist-outfit.md). Pete picked the 1920s lady cyclist and seed 21.

**The outfit:**
- green felt cloche with a mustard ribbon and bow;
- cream blouse with a Peter Pan collar and a green ribbon bow;
- mustard rib-knit cardigan with brown buttons;
- knee-length knife-pleated brown herringbone skirt;
- green and cream argyle knee socks;
- brown T-bar shoes;
- cream gloves.

**Result:** `out/outfit_female_cyclist-goose/outfit_female_cyclist_full_dressed.glb` (glTF validator: 0 errors,
0 warnings; three.js r161: ok). Each garment also exists alone on the naked female goose as
`outfit_female_cyclist_only_<piece>_dressed.glb`. Sheets are in `docs/img/cyclist/lady_*`.

## Pipeline (same as his, plus the female body)
1. **Her body:** `chars/outfit_female_cyclist.json` uses the `outfit_female` slider shape (the shared base mesh with
   her proportions).
   - The naked shaped body comes from `dress_goose.py --char outfit_female_cyclist --tag naked`, rendered in the key
     cameras with `outfit_beauty.py --cams`.
   - Three fronts were generated (seeds 7 / 21 / 42), seed 21 was picked, then its left and rear views were made
     (`refs/outfit_female_cyclist/t2i/key1`).
2. **Build frame:** her garments are built on the slider-shaped body *before* dress_goose lifts the soles to the
   floor (+0.0932 m).
   - `build_frame_lift` in the recipe records this. All the recipe heights are in that frame, and so is
     `joints_file`.
   - `outfit_beauty.py --with-lift` previews loose shells.
   - `make_boot.py` has `z_off`.
3. **Build:** `CHAR=outfit_female_cyclist bash scripts/build_cyclist.sh` (all pieces, in layering order):
   - **shirt:** blouse, tucked.
   - **cardigan:** `make_garment` kind shirt, plus:
     - `hem_points` and the new `v_neck` (a V opening cut along the field);
     - `knit` (ribbed hem, cuffs and V band; no blousing; no cufflink);
     - `button_top`.
   - **skirt:** `make_skirt.py`, now without the Victorian guide, bustle, flounce or apron. Extra options:
     - `pleats` (knife-pleat sawtooth in the silhouette, stitched down to `z_stitch`, with creases in the detail);
     - `skip_tail` (the radius ignores the tail).
   - **socks:** kind boot with `min_r`: a knitted tube no thinner than 3.4 cm round the goose's thin ankle. The
     argyle had pinched and torn there.
   - **boots:** the T-bar shoe. It is short; the webbed foot is hidden under it anyway.
   - **hat:** new `make_cloche.py`: a bell crown fitted to the head, a downturned brim, a grosgrain band and a flat
     bow.
   - **pancollar:** new `make_accessory --piece pancollar`: rounded collar lobes and a ribbon bow.
   - **Painting** (`pattern_paint.py`):
     - `rib` with `arms` (ribs follow each sleeve);
     - painted `buttons`;
     - `argyle` on the socks (per-leg axes, overcheck);
     - `brogue` with `tbar`, `laces: false`, `wing: false`;
     - `glove` with `holes: false`;
     - `flat_nz`: the skirt's shelf over the rump and the sock flare aren't flat tops.
     - Herringbone on the skirt uses true arc length (`r0` 0): at a fixed radius the columns made a starburst at
       the back.
4. **Full-outfit variants** (`shells/variants/withshoes`, dressed with `--variant withshoes`):
   - socks trimmed inside the shoes;
   - blouse trimmed above the cardigan hem and cropped to the V-neck panel (`with_outfit.trim_below` / `keep_box`
     via `trim_edge.py` / `crop_shell.py`). Its sleeves poked through the cardigan's shoulders when seated.
   - The standalone blouse and socks stay whole.
5. **Dressing**, with per-character keys:
   - `layer_ignore`: cardigan, blouse, skirt, socks;
   - `force_hide`: the skirt hides the tail;
   - `skin_merge`: cardigan;
   - `chain_follow` / `chain_drape`: the skirt's cloth chains ride the thighs when seated, the back included.
6. **Judging:** `CHAR=outfit_female_cyclist bash scripts/review_cyclist.sh <tag>`, with reviewer agents each round
   (v3, v7, then the final checks). Fixed along the way:
   - the dark hole in the V-neck;
   - torn socks at the ankle;
   - clown-length shoes;
   - the starburst on the back of the skirt;
   - the blouse poking through the cardigan at the back hem and the shoulders;
   - the skirt tenting when seated;
   - the cloche reading as a bowler.

## Limits / next
- The gloves follow the goose's mitt hands; the reference shows fingers.
- The Peter Pan collar reads as a band more than two lobes. The cardigan cuffs are a little full.
- In the raw dressed GLB, the riding pose leaves the skirt's cloth chains at rest in three.js, because constraints
  don't export. They follow the thighs once `ride_fit.py` bakes the riding clips, as with the Victorian coat tails.

## Revisions r1-r3 (Pete: darker mustard matching his, socks over the knees, hat higher and tipped back)
- **Mustard:** the cardigan uses his vest's mustard. Its base colour is scaled to [138,101,37] so the RENDERED colour
  matches his (median 193,144,65 against his 195,146,66); the knit rib shading lifts the base about 8%. The cloche
  ribbon and the sock overcheck lines use the same mustard.
- **Socks** over the knee, up under the skirt hem (z_top 0.565 dressed): no leg shows, standing or seated. The minimum
  radius now runs up past the knee and `outer_smooth` is 90, so the goose's knobbly knee no longer shows through.
- **Hat:** band 1.2 cm higher (`band_z` 1.64). The new `tilt_back_deg` (9 deg) in `make_cloche.py` tips it back:
  the front of the brim rises, pivoting about the band centre.

## Seated skirt drape (Pete: "when riding why is the skirt up high and not down on the legs?")
- **Cause:** every skirt chain bone took about 95% of the thigh's rotation down to the hem. Seated, the whole skirt,
  hem included, swung forward and up with the thighs, and the side panels stuck out like wings.
- **Fix:** `chain_follow` / `chain_drape` now drape. The front follows the thigh to the knee, then the hem hangs
  (1.0 / [1.0, 1.0, 0.5]). The sides follow 0.9 with [1.0, 0.8, 0.45]. The back follows 0.85 with
  [1.0, 0.85, 0.55], so it rests on the seat instead of hanging through the saddle.
- Sheet: `docs/img/cyclist/lady_seated_drape.png`. `POSE_RES=w,h` makes dress_goose render larger pose sheets.
