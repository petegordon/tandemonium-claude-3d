# Props from one photo (first: ketchup bottle, 2026-10-17)

Photo -> clean reference views -> generated hi-poly (shape only) -> ray-cast quad grid low-poly -> texture painted
from the reference views (labels stay sharp; generator textures smear text).

```
PY=/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe   # ComfyUI :8189 running
$PY scripts/prop_views.py --prop ketchup --photo refs/ketchup/photo.jpg          # Qwen-Image-Edit: front/left/rear/right (refs/ketchup/prop.json)
cp refs/ketchup/t2i/v1/{front,left,rear}.png -> refs/ketchup/<view>_raw.png      # (+ right -> right_drawn_raw.png)
$PY scripts/comfy_job.py prep --char ketchup --right drawn
$PY scripts/comfy_job.py single --char ketchup --view front --model trellis --seed 42   # picked over pixal-mv (better depth)
$PY scripts/prop_decals.py --prop ketchup                                         # label decals, cap line, plastic colour
blender -b --factory-startup --python scripts/prop_lowpoly.py -- --prop ketchup --mirror-y --hi <trellis textured.glb>
node tools/threejs_check/prop_check.mjs out/props/ketchup/ketchup_lod0.glb renders/ketchup/threejs_lod0.png
```

Output `out/props/ketchup/`: `ketchup_lod0.glb` (2432 tris), `ketchup_lod1.glb` (704 tris), `ketchup.blend` (LODs + the
hi-poly in collection "Hi", hidden), `textures/` (2048 albedo + ORM). 0.195 m tall, origin at the cap's base centre,
one material with clear coat (KHR_materials_clearcoat). glTF validator: 0 errors / 0 warnings.

Notes: the side views from Qwen drift to 3/4 (label wraps), so only front + rear feed the texture; the generators'
depth is a guess -> `--depth-ratio` (0.64 = real 20 oz squeeze bottle). `--plastic-gain` brightens the photo's
shaded red into a PBR albedo. Rear nutrition panel is AI-invented (illegible fine print).
