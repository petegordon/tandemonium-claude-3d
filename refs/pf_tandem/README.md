# Penny-Farthing tandem (Time Warp bike) — approved reference set

Approved by Pete 2026-11-06. Two copies of one penny-farthing back to back, riders facing away from each other,
joined by one straight decorative cross bar (black lacquer, gold filigree, goose medallion) at mid backbone height.

- `pick/left.png`: side view (the 3D pipeline's left view). `pick/right.png` is its mirror.
- `pick/front.png` = `pick/rear.png`: end view, wheel edge-on (the bike is symmetrical end to end).
- `pick/half_look.jpg`: the single penny-farthing Pete picked as the half.
- `half_rgba.png`: that half keyed out of its background.

How the side view was made:
1. `scripts/pf_join.py` keys the half.
2. `scripts/pf_crossbar.py --gap 202 --y 560` mirrors the half and draws the straight bar.
3. `scripts/pf_bar_polish.py` has Qwen restyle only the bar.

The end view comes from `scripts/pf_endguide.py`: an edge-on guide drawn in code, which Qwen then repaints.
