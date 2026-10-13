# Text-to-image reference views (2026-10-13)

Pete: generate the garment-on-goose reference views from words instead of drawing them; local first, ChatGPT/Codex
if that is not good enough. First outfit: a 1920s cyclist (flat cap, shirt + tie, argyle vest, plus-fours with knee
straps, knee socks, brogues, driving gloves) -- `refs/outfit_male_cyclist/t2i_prompt.json`.

## Views needed
The garment pipeline reads **front, left, rear** (the right = the left mirrored, `ref_dress.py`); the 3/4 is only for
looking. Picked set: `refs/outfit_male_cyclist/t2i/pick/` (front, left, rear, right_mirrored, sheet.png).

## How (local, Claude's ComfyUI :8189)
1. Naked base goose, tail removed (clothes hide it; the model otherwise kept it poking out of the trousers):
   `blender ... outfit_beauty.py -- --glb out/base-goose/base_goose_rigged.glb --out renders/t2i/base_views_notail.png
   --px 1024 --floor 0.6 --views front:0,q34:35,left:90,rear:180,right:270 --hide-bones Tail`
2. `python scripts/t2i_outfit.py --outfit outfit_male_cyclist --tag <t> --seed 21 --base "renders/t2i/_base_views_notail_{view}.png"`
   Qwen-Image-Edit-2511 (unsloth Q4_K_S GGUF via ComfyUI-GGUF) + Lightning 4-step LoRA, cfg 1: the FRONT is dressed from
   the words; every other view gets picture 1 = that naked view, picture 2 = the dressed front ("the identical outfit").
   ~56 s front, ~72 s per other view, peak ~10.3 GB VRAM. `--front <png>` reuses a chosen front; `--views` picks views.
3. Fixes that mattered: tail removed from the input; "no belt" / "its own strap below each knee"; for the sides "the
   plus-fours follow the body's silhouette, no bulk behind the hips" (the model invented a bustle).

## Known limits
- The model re-proportions the goose a little (narrower shoulders, more human arms); the part-to-part warp absorbs
  that as it did for Pete's drawings.
- It sometimes flips the facing of a side view (the "right" came out facing left) and re-adds a tail in the 3/4.
- Output ~800 x 1330 px per view.
