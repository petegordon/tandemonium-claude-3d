"""Helmet design examples for the robot outfit (Tandemonium #611): the picked A2 robot goose with a full helmet added.

  python scripts/robot_helmet_prompts.py   -> refs/outfit_male_robot_helmet_<design>/t2i_prompt.json
then, per design (picture 1 = the already-dressed key views, so only the helmet is new):
  t2i_outfit.py --outfit outfit_male_robot_helmet_<d> --seed 7 --views front,left \
      --base refs/outfit_male_robot/t2i/key1/{view}.png
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUIT = json.loads((ROOT / "refs/outfit_male_robot/t2i_prompt.json").read_text(encoding="utf-8"))["outfit"]
STYLE = ("Photorealistic 3D character render, soft studio lighting, real materials. Keep the whole robot suit exactly as it "
         "is in picture 1; the only change is the helmet on the goose's head. The helmet fits the goose's own head shape "
         "and sits on top of the long black neck, which stays visible down to the chrome collar ring. The goose has NO tail.")
HINT = {"front": "Keep the arms and legs exactly where they are in picture 1.",
        "left": "Side profile: show the helmet's full shape from the side. Keep the feet and legs exactly where they are in picture 1."}
HELMETS = {
    "bubble": "a clear glass dome helmet, like a 1950s space-age fishbowl, enclosing the goose's whole head, with a polished "
              "chrome ring at its base around the top of the neck and a short chrome antenna with a blue light on top; the "
              "goose's head, eyes and beak are fully visible through the glass",
    "visor": "a white enamel full robot helmet covering the whole head, shaped to the goose's skull, with a wide wrap-around "
             "glowing blue visor band across the eyes, chrome side discs where the ears would be and thin blue light strips; "
             "the goose's black beak sticks out through an opening at the front",
    "goosebot": "a full robot head that encases the goose's head and beak completely: polished chrome shaped exactly like a "
                "goose's head and bill, with a white enamel cheek panel where the goose's white cheek patch is, two round "
                "glowing blue eyes, a visible hinge line where the bill opens, and small rivets",
    "racer": "a white aerodynamic time-trial cycling helmet with a long pointed tail sweeping back over the neck, a mirrored "
             "blue visor that wraps around over the eyes, chrome trim, a glowing blue light strip along the top ridge and a "
             "chrome chin strap; the goose's black beak stays free below the visor",
}
for d, helmet in HELMETS.items():
    p = ROOT / "refs" / f"outfit_male_robot_helmet_{d}"
    p.mkdir(parents=True, exist_ok=True)
    (p / "t2i_prompt.json").write_text(json.dumps({
        "note": f"Pete 2026-11-07: helmet design example '{d}' for the robot outfit's hat slot.",
        "outfit": f"{helmet}; worn with {SUIT}", "style": STYLE, "view_hint": HINT}, indent=1), encoding="utf-8")
    print("wrote", p)
