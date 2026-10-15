# Goose Studio: animations, wardrobe store and reels (plan, 2026-10-15)

**Goal:** one three.js app that shows off everything we've built: the rigged geese, eyes that look
around and blink, the honk (jaw, tongue and sound), every garment and colourway, and the tandem.
The same app does two jobs:

1. **Wardrobe store.** Interactive. Pick a goose, try garments on slot by slot, change colourways,
   poke the goose (it honks, its eyes follow the cursor).
2. **Reel director.** Scripted shots rendered frame-exact to MP4 (9:16 for Shorts/TikTok/Reels,
   16:9 for Steam/X). This feeds the launch plan's open problem: *what to post*.

Status (2026-10-15): **Pete answered §8; v1 built** (see §9).

**Pete's decisions (2026-10-15):**
- Q1: showcase / lookbook, no economy.
- Q2: tools inside Tandemonium, one for the store and one for the animations.
- Q3: try sharing hats and accessories.
- Q4: build the proposed clips.
- Q5: game music is fine; Claude picks the reels (intro + "It's watching you" + "Getting dressed").
- Q6: clean backdrop.
- Q7: Claude's call (spring bones on the cloth chains and tail).
- Q8 (intro ending): unanswered, so it ends on a hold, with the Victorian pair as the default cast.

---

## 1. What we already have

| Asset / system | Where | State |
|---|---|---|
| Base goose, 35-bone standard rig (Mixamo names + Jaw, Tongue, Eye_L/R, EyelidUpper/Lower, tail, chains) | `out/base-goose/base_goose_rigged.glb`, release `base-goose-p2-rigged` | Done |
| Face clips `idle` (2 s), `blink` (0.5 s), `look_around` (3 s), `honk` (1.25 s: neck stretch, jaw 30°, tongue out) + `pose_*` | `scripts/make_anims.py`; shipped in **every** rider GLB | Baked in Blender; **not used in the game yet** |
| Eye asset: eyeball + lids + catchlight, identical on all geese | `assets/goose_eye/`, `eye_states_glb.py` | Done. Lid axes in `base_rig.json` |
| Outfits: Original M/F, Victorian gent, Victorian lady, Cyclist M/F | `out/<char>-goose/<char>_full_dressed.glb` | Done, validator-clean |
| **Single garments on the naked goose**, rigged | `dress_singles.sh` → `<char>_only_<piece>_dressed.glb` (cyclist: boots, breeches, gloves, hat, necktie, shirt, socks, waistcoat) | Done for the cyclist; Victorian/original need the same run |
| Colourways (3 per pair, HSV remap per material) | `out/delivery/goose_colourways.json`, game `js/goose-colourways.js` (shader) | Done in game |
| Cloth chains for coat tails / skirts (D12) | `<char>_cloth_chains.json` | Baked into riding clips only |
| Tandem + riding clips (`Pedal`, `WheelSpin`, `Ride_/Lean_L_/Lean_R_<seat>`) | `out/delivery/goose_tandem.glb`, riders | In game, PR #406 |
| Honk audio, incl. onset detection for a honk bank | game `assets/goose-honk.mp3`, `js/audio-engine.js` | Done |
| Headless three.js render (puppeteer + r161) | `tools/threejs_check`, `tools/ride_harness/shots.mjs` | Done |
| ffmpeg | WinGet, on PATH | Available |

**Gaps:**
- No body-only animations: walk/waddle, turn, wave, bow, hat-tip, twirl, mount the bike.
- Eyes and honk only exist as fixed clips. Nothing drives them live (look at the cursor or camera,
  random blinks, honk on demand).
- Garments only exist as whole dressed GLBs, each with its own skeleton copy. Nothing can mix pieces
  at runtime.
- Cloth chains hang still except in the baked riding clips.

---

## 2. Architecture (recommended)

```
tools/goose_studio/            (new; same pattern as ride_harness: static server, three r161 from CDN)
  serve.mjs                    :8191, serves out/studio/** + the app
  index.html  studio.js        store UI + viewport
  rig/        wardrobe.js      body + garment GLBs → ONE skeleton (SkinnedMesh.bind), body masks
              face.js          procedural eyes, blinks, honk (jaw/tongue/neck + audio + beak sync)
              springs.js       spring bones on cloth chains, hat plumes, necktie (secondary motion)
              mixer.js         layered clips: base body clip + additive face/upper-body + springs
              colourways.js    copied from the game's shader HSV remap (same data JSON)
  director/   reel.js          timeline JSON → camera, clips, garment swaps, honks, captions
              capture.mjs      puppeteer: fixed-dt frame stepping → PNG frames → ffmpeg MP4 (+ audio mux)
  reels/*.json                 one file per reel
scripts/
  export_wardrobe.py           Blender: per-garment GLBs WITHOUT skeleton copies + wardrobe.json manifest
  make_anims.py (extended)     new body clip library (§4)
out/studio/                    bodies, garments, clips, manifest (gitignored; GitHub release when stable)
```

Why three.js and not Blender/Eevee for the reels: the reels then show **exactly what the game
renders**. The same scene code serves the store and the reels (and later the game), and a reel is a
re-runnable JSON file, so tweaking a shot means editing a file, not re-rendering a .blend by hand. A
Blender "hero" render path stays possible later for a trailer.

### 2a. Wardrobe asset contract (the key technical piece)

- **Two bodies:** `body_male` (base + legs ×1.15 sliders) and `body_female` (slider body, D11).
  Garments are built per body, so cross-wearing is out of scope for v1 (see Q3).
- **One GLB per garment** per body: skinned to bone *names* only. On load the studio rebinds it to
  the body's skeleton, so 10 garments don't mean 10 skeletons.
- **`wardrobe.json` manifest**, one entry per garment:
  `{id, body, slot (head|neck|torso_inner|torso_mid|torso_outer|hands|legs|feet|socks),
  hides: [body mask ids], conflicts/requires, chains, colourway materials, outfit sets, thumbnail}`.
- **Body masks:** `dress_goose` already makes hidden body regions (tail, toes, thighs) into toggle
  sub-meshes. Export them as named primitives, and the studio hides the union of the worn garments'
  `hides`.
- **Layering rules come from the builders,** not new design. The `--without coat,waistcoat`
  variants and the `withshoes` sock trim already encode which combinations are valid. Rare
  combinations (socks without shoes) get their own variant GLB.
- **Gate:** a mix-and-match fixed set (e.g. cyclist cap + Victorian coat on the male) renders with no
  poke-through in 4 views × 3 poses. This is the same check as Pete's per-piece review (alone, on the
  naked goose, recoloured, riding).

---

## 3. Face and personality runtime (the "alive" layer)

All procedural in `face.js`, playing on top of whatever body clip runs:

| Feature | Behaviour | Built from |
|---|---|---|
| **Eye look-at** | Eyes lead and the head follows with a lag: eyeballs clamp at ±25° yaw / ±15° pitch, then Head/Neck take the rest. Lids track pitch so they don't clip. Targets: cursor (store), camera (reels), the other goose (duets). | Eye bones + axes in `base_rig.json` |
| **Saccades** | Small random jumps every 0.4–2 s while the target is still | — |
| **Blinks** | Random 2–6 s apart, plus one on every big gaze shift, sometimes doubled | Lid bones (`blink` clip as the shape reference) |
| **Honk** | Triggers on click or the timeline. Neck stretch, jaw open, tongue out; plays a random honk from the honk bank. **The jaw follows the audio envelope** (open on each onset), so long honks flap | `honk` clip + `audio-engine.js` onset code |
| **Startle** | A honk nearby: the other goose blinks, eyes go wide (lids up), and its head jerks | Lids + additive neck |
| **Idle** | Breathing + sway, plus occasional weight shifts | `idle` clip |
| **Secondary motion** | Spring bones on coat tails, skirt chains, hat plume, necktie, tail | `<char>_cloth_chains.json` (D4/D12: chains, not cloth sim) |

**Gate:** a 20 s capture of an idle goose looking at a moving target reads as alive, with no lid
clipping or popping. Pete reviews the GIF.

---

## 4. New body clip library (Blender, `make_anims.py` extended)

Hand-keyed on the standard rig: one script and one rig, so every outfit gets every clip. Proposed
v1 set (Pete picks, Q4):

| Clip | Length | Used for |
|---|---|---|
| `waddle` (in-place walk, plus root motion variant) | 1.0 s loop | Store entrance, runway |
| `walk_start` / `walk_stop` (into and out of the waddle cycle) | 0.6 / 0.8 s | Intro reel, store entrance |
| `turn_to_camera` (90° in-place turn, L and R mirrored; eyes lead, then head, then body) | 1.0 s | Intro reel |
| `turn_show` (quarter turns with a pause, "model on a runway") | 4 s | Store try-on, reels |
| `twirl` (360° spin, cloth chains fly out) | 1.5 s | Skirt/coat showcase |
| `hat_tip` (gent) / `curtsy` (lady) / `bow` | 1.5–2 s | Victorian reels, store "purchase" beat |
| `wave` (mitten) | 1.5 s | Greeting |
| `admire` (looks down at itself, smooths the coat) | 2.5 s | Store try-on reaction |
| `flap_startle` (arms up, feathers) | 1 s | Comedy beat; matches the game's goose strike |
| `mount_bike` / `dismount` | 2 s | Ties the store to riding |
| `celebrate` (hop + honk) | 1.5 s | Endings |

Rules: face bones are excluded from body clips (the face layer owns them). The game's
per-clip bone filtering (riders lesson: the exporter samples every bone) applies here too. Every clip
gets checked in the three.js harness, not just Blender.

**Gate per clip:** contact sheet + a looping GIF, and the feet don't slide (`feet.mjs`).

---

## 5. Store experience (interactive)

Layout: the goose on a round plinth (Victorian tailor's shop styling: wallpaper, mirror, dress form
optional), a slot rail down one side, and a colourway swatch row.

- **Try-on:** click a garment, the goose plays `admire`, and the piece pops on with a squash beat.
  The body masks update.
- **Outfit sets:** Original / Victorian / Cyclists / Fancy as one-click presets (the game's pairings).
- **Colourways:** the same swatches as the game.
- **Interact:** the eyes follow the cursor; click the goose to make it honk; drag to orbit;
  double-click to `twirl`.
- **Pair view:** both geese side by side, or seated on the tandem with pedalling.
- **Photo mode:** hide the UI, pick a pose, save a PNG (shareable).
- **Economy (Q1):** shown as plain prices in Chaos Coins? No prices at all (a lookbook)? Or wired into
  the game's progression later? **This is Pete's design call; v1 builds no economy logic.**

**Gate:** Pete plays with it locally (`node tools/goose_studio/serve.mjs`), then a Cloudflare Pages
preview if he wants to share it.

---

## 6. Reel director

- A reel is a JSON timeline: `{aspect, fps, duration, cast:[{goose, outfit, colourway}],
  set, shots:[{t, camera:{preset|path}, actions:[clip|honk|lookAt|equip|colourway|caption]}],
  audio:[{t, file}]}`.
- `capture.mjs` drives headless Chrome with a fixed timestep (no wall clock, so the output is
  deterministic). It writes PNG frames, then ffmpeg encodes H.264 MP4 (1080×1920 and 1920×1080) and
  muxes the honks and music. Audio events are rendered offline from the same timeline, so they stay
  in sync.
- Camera presets: turntable, push-in to the eyes, low hero angle, over-the-shoulder, selfie-cam
  (matches the game's front view).

**Reel slate v1** (6–15 s each, built to loop):

0. **"Intro" (Pete, 2026-10-15)**: the male enters from the left edge of the frame and the female
   from the right, both waddling. They slow and meet in the middle, glance at each other, then both
   turn to face the camera. This is the opener for the store and the reels.
   - **Beats (~8 s):**
     - 0–0.5 s: empty set.
     - 0.5–4.5 s: both walk in. Their steps are offset by half a cycle so they don't march in lockstep.
     - 4.5–5.3 s: `walk_stop`. Each settles one stride from centre.
     - 5.3–6.3 s: eyes lead and the heads follow to look at each other; one blink.
     - 6.3–7.3 s: `turn_to_camera` (90° turn in place, eyes snap to the lens first).
     - 7.3–8 s: hold on the camera with a breath idle. Optional end beat: hat tip and curtsy, a
       double honk, or a title card (Q8).
   - **Camera:** locked-off wide at goose eye height, framed so the meeting point is centre-screen.
     The 9:16 cut uses a tighter lens, and the entrances start just outside the frame edge.
   - **Mechanics:** root motion comes from the clip's stride length, so the feet don't slide. The
     director computes each goose's start x from the frame edge (from the camera frustum at the
     goose's depth) and the walk speed, so both arrive on the same beat. A foot-plant check (adapted
     from `tools/ride_harness/feet.mjs`) runs on the capture.
   - **Variants for free:** any outfit pair (Victorian, Cyclists, Fancy, Original) and any colourway,
     so one timeline gives 4+ openers.
1. **"Getting dressed"**: the naked goose, then garments drop on one by one in time with the beat,
   then a hat tip and a honk. One per outfit (×4).
2. **"It's watching you"**: an extreme close-up of the eyes following the camera, a blink, then a
   honk straight into the lens.
3. **"Colourway roulette"**: every honk swaps the colourway.
4. **"Runway"**: waddle, `turn_show`, `twirl` with the skirt flaring.
5. **"Honk duet"**: the captain honks, the stoker startles, and they honk back and forth faster and
   faster.
6. **"Mount up"**: dressed in the shop, `mount_bike`, then pedal off on the tandem (a turntable of
   the pair riding).

Gameplay footage reels (the actual game) are separate. This slate is the character/wardrobe side.

**Gate:** the intro (reel 0), reel 2 and reel 1 (Victorian) rendered at full quality. Pete judges them as posts.

---

## 7. Phases

| # | Phase | Output | Size | Gate |
|---|---|---|---|---|
| S0 | **Wardrobe export**: `export_wardrobe.py`, per-garment GLBs for all 6 outfits (`dress_singles` for Victorian + original), `wardrobe.json`, body masks as primitives | `out/studio/` | M | Mix-and-match set renders clean in three.js |
| S1 | **Studio shell**: server, loader, rebinding, masks, colourways, orbit, outfit presets | `tools/goose_studio` | M | Every full outfit in the studio matches its `_full_dressed.glb` render pixel-close |
| S2 | **Face runtime**: look-at, saccades, blinks, honk with audio + beak sync, startle, springs | `face.js`, `springs.js` | M | 20 s "alive" GIF approved |
| S3 | **Clip library**: the §4 clips, Pete's picks first | `make_anims.py` → `base_goose_clips.glb` (clips only, retargeted by name) | L | Per-clip sheets + GIFs |
| S4 | **Store UX**: try-on flow, swatches, pair view, photo mode, set dressing | studio | M | Pete plays it |
| S5 | **Reel director + capture** | `director/`, `reels/*.json` | M | Reels 1 + 2 posted-quality |
| S6 | **Reel slate + delivery**: remaining reels, GitHub release, optional Pages deploy, notes on bringing face runtime into the game | MP4s, release | M | Pete's call per reel |

S2 can run alongside S0/S1. S3 is the long pole (hand-keying), so start it early with the clips the
intro needs (`waddle` with root motion, `walk_start`/`walk_stop`, `turn_to_camera`), then
`turn_show`, `hat_tip`, `twirl`. **The intro is the first end-to-end target:** it exercises the
full-outfit loading (S1), the eyes and blinks (S2), walking clips (S3) and capture (S5) without
needing the store UI, so it can ship before S4.

**Game spin-off (later, not in scope):** `face.js` is engine-agnostic three.js, so riders could blink,
look at the other player and honk on a button in the game. That would be a game design change for
Pete to decide.

---

## 8. Questions for Pete

1. **Store meaning:** is the "garment store" a showcase/lookbook (website + reels), or the start of an
   **in-game** shop (Chaos Coins, unlocks)? v1 builds the showcase either way, with no economy logic.
2. **Where it lives:** standalone (Cloudflare Pages, e.g. a `studio.` subdomain, shareable link for
   posts) or a menu screen inside Tandemonium? Recommended: standalone first, using the same code.
3. **Cross-wearing:** may the male wear lady pieces (hats, at least), and vice versa? Hats and
   accessories are cheap to cross-fit. Bodices and skirts on the male body mean a re-fit per piece.
4. **Clip picks:** which §4 clips after the intro set? Recommended: `turn_show`, `hat_tip`/`curtsy`,
   `twirl`.
5. **Reels:** the intro is first. Which next? Recommended: "It's watching you" + "Getting dressed
   (Victorian)".
   Music: one of the game's tracks (licence OK for social?) or honks only?
6. **Set style:** a Victorian tailor's shop, or a clean studio backdrop (colour-keyed per outfit)?
   Recommended: clean backdrop for v1 reels (fast, readable on phones), the shop later.
7. **Spring bones on coats/skirts:** OK as "not cloth sim" under D4? (Bone chains with damped
   springs; the mesh can't break.)
8. **Intro ending:** just face the camera and hold (as described), or add a beat: hat tip + curtsy,
   a double honk, or the Tandemonium title dropping in? And which pair is the default intro cast?
   Recommended: the Victorian pair, ending on a hold, so it can lead into any other reel.

---

## 9. v1 as built (2026-10-15)

| Piece | Where | Notes |
|---|---|---|
| Body clips | `scripts/show_clips.py`, `scripts/bake_show.sh` -> `out/show/<goose>_clips.glb + .json` | Parametric poses (pelvis / feet / spine / wrists / hat) solved by aims + two-bone IK on each DRESSED goose; 14 clips: idle_shift, walk_start / walk / walk_stop (0.53 m/s waddle, root motion), turn_L90 / turn_R90, twirl, hat_tip (lifts the hat via HatSocket), curtsy, bow, wave, admire, celebrate, flap_startle. Armature-only GLBs (~0.5 MB each). `--render` + `show_sheet.py` = Workbench contact sheet. |
| Game tools | tandemonium branch `feat/goose-studio` (worktree `../tandemonium-studio`, from `feat/goose-riders-p5`), LOCAL | `goose-wardrobe/` lookbook; `goose-stage/` reel director + clip lab; shared `js/goose-studio/goose-actor.js` (segments, root motion, face, springs, wardrobe, borrowing) + `studio-scene.js` (cyclorama, lights, honk sampler). Clips copied to `tandem-3d/goose/show/`. |
| Reels | `node scripts/goose-reel.mjs <intro|watching|dressed> [9x16|16x9] [--pair ..] [--goose ..] [--fps 30]` -> `renders/goose-reels/*.mp4` | Page steps itself (no clock shim), CDP screenshots; honks logged by the page, music + honks mixed by ffmpeg. ~13 captured fps at 1080x1920. |

Runtime notes: hats are re-weighted Head -> HatSocket at load; part names drop Blender's `.001` (`hat001` -> `hat`);
the lady geese's armature node isn't called `goose_rig`, so it's found as the Hips' parent. Face bones are never keyed
in body clips; the face layer owns them (eyes = look-at with lag + saccades; lids = the rider's blink clip;
jaw/tongue = its honk clip; neck = honk additive).

Open:
- Pete's review of the 3 reels and both tools.
- Mount/dismount clip (needs the bike in the studio).
- Lids following eye pitch.
- A honk with more neck lunge for the close-up.
- Borrowed neckwear fit (untested on every pair).
