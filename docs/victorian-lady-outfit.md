# Victorian lady (female goose), partner to the original male (2026-10-13)

**Pete's brief:** a female "more like the original male, not as fancy", wearing a dress, "more dressed up than the cyclist, but less fancy than the female original; taken from the style of the original male". The pairs are now **Victorian** (original male + this lady), **Cyclists** and **Fancy** (Fancy gent + the red-dress lady).

**References:** text to image (`refs/outfit_female_victorian/t2i_prompt.json`).
- Three fronts were generated (`docs/img/victorian_lady/fronts.jpg`). Pete picked seed 21.
- Side and back views come from seed 21 in the key cameras (`t2i/key1`).

**Outfit:**
- brown tweed walking dress: a fitted jacket bodice with lapels, puffed sleeve heads and white cuffs, open over a dark red waistcoat with brass buttons;
- white collar with a black bow tie;
- A-line mid-calf skirt with a cream hem band;
- black stockings and black lace-up ankle boots;
- black gloves;
- small brown bowler with a dark red band and a brown feather.

**Build:** `CHAR=outfit_female_victorian bash scripts/build_cyclist.sh bowtie waistcoat jacket skirt socks boots gloves hat`, then `dress_goose.py --char outfit_female_victorian --tag full --variant withshoes`.
- **Recipe:** `chars/outfit_female_victorian.json` (built by hand from the lady cyclist's recipe plus the male recipes). Her upper-body joints equal the base body's, so these carry over unchanged:
  - the original male's bowler fit;
  - the Victorian male's bow tie + collar (`make_accessory --piece bowtie`, black bow, all-white collar);
  - the male cyclist's waistcoat construction.
- **jacket:** shirt kind with `v_neck` reaching below the hem (always open).
  - New `ease.waist_nip`: fitted waist; `nip_min` keeps it outside the waistcoat.
  - `ease.puff` gives the sleeve heads.
  - Painted herringbone with `arms` (columns run along the sleeves).
  - `bands`: lapels, and white cuffs (`abs_x_min` picks the sleeve ends, not the hem).
- **waistcoat:** in the full outfit only the panel in the jacket's opening is kept (`with_outfit.keep_box` + `bisect`: `crop_shell.py --bisect` cuts along the box planes, so the edge is clean). The rest poked through the fitted jacket.
  - Painted buttons sit where the builder moulds them (`buttons` / `button_top` / `button_step` aligned).
- **skirt:** `make_skirt.py`, A-line, no pleats. The cream band is a `bands` entry with `offset` (set back from the hem).
- **boots:** `make_boot.py` ankle shaft. The brogue painter's new `shaft_laces` paints laces and eyelets up the shaft front.
- **hat:** `make_hat.py` (bowler). New `plume.palette` gives a brown feather instead of the default gold.
- **Rounds:** r1–r8 (`renders/cyclist/outfit_female_victorian/`), one reviewer-agent round (r4: 6/10). The fixes after it:
  - waistcoat crop;
  - fitted jacket;
  - aligned buttons;
  - clean edges;
  - ankle boots with laces;
  - wider hem band.
- **Checks:** glTF validator 0 errors / 0 warnings; three.js r161 ok. Each garment also exists alone on the naked goose (`dress_singles.sh`).

**Riding:** stoker behind the original male: `ride_fit.py --char outfit_female_victorian --dressed-tag full --seat Stoker --riding-hem 0.72,0.84,0.94 --side-lean 30 --clips`.
- 0 mm contact error.
- 20–27 skirt vertices inside the rear wheel's disc (the original lady: 21, on the mudguard).
- Game file: `goose_stoker_victorian.glb` (6.2 MB).

**Colour changes:** `docs/img/colourways.jpg`. Each pair is shown in its own colours plus three colourways (`refs/colourways.json`).
- Renders: `scripts/colourway_renders.py`, then `scripts/colourway_sheet.py`.
- `outfit_beauty.py --recolour file:way:seat` remaps each garment by hue / saturation / value from the colour under its UVs (texture × baseColorFactor), so the weave, argyle, buttons and seams stay.
- This is a review preview. The game would need per-garment tint masks or texture variants (ROADMAP P3.6).
