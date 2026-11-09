# Gold Standard tandem (Tandemonium #611)

The all-100 reward bike, traced from Pete's side ref (`refs/gold_standard/pete_refs/side.png`, plus front/rear/top).
Built in code on the game tandem's rig (`out/bike/bike_rigged_goosefit26.blend`), so every goose outfit fits it.

```
blender -b --factory-startup --python scripts/make_gold_standard.py -- [--sheet --views a,b --samples 48]
```

| build | flags | tris | file |
|---|---|---|---|
| full | (none) | ~140k | `out/gold_standard/gold_standard_tandem.glb` (renders, review) |
| game | `--game` | ~88k | `..._tandem_game.glb` → Tandemonium `tandem-3d/goose/gold_standard_tandem.glb` |
| master | `--tag master --frame-tris 2000000` | ~1.05M | `..._tandem_master.glb` (Google Drive: House Tandem/Tandemonium/3D/Gold Standard) |

`--game` decimates the frame to 24k (custom normals from the full sculpt), collapses the panel engraving to ~35%,
and uses 20 segments round the saddles instead of 32. No Draco: the game's chooser preview loads GLBs without it.

How the frame is made (mask, core sculpt, crown panel, engraving, saddles): see the comments in the script and the
review tools `scripts/gs_*.py`.
