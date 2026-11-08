"""Write the robot-outfit look variants (Tandemonium #611 player bots: the Canada Goose bot) as t2i prompt files.

  python scripts/robot_prompts.py   -> refs/outfit_male_robot_<look>/t2i_prompt.json for chrome, brass, canada

Pete picks one look; it then becomes refs/outfit_male_robot (and a female version) for the normal outfit chain.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = ("Photorealistic 3D character render, soft studio lighting, real materials. The goose wears a fitted robot suit like "
         "armour over its body: every plate follows the goose's own body shape closely, with dark flexible joints at the "
         "shoulders, elbows, knees and waist so it could ride a bicycle. No weapons, no wings added, no cape, no jetpack. "
         "The goose keeps its own head exactly: black head and neck, white cheek patch, eyes and beak unchanged, not covered. "
         "The goose has NO tail.")
HINT = {
    "front": "Keep the arms and legs exactly where they are in picture 1.",
    "rear": "From the back: the back plate with its power pack close to the body, the backs of the arm and leg plates and the boots.",
    "left": "Side profile: plates close to the body, the power pack flat against the back (no bulk). Keep the feet and legs exactly where they are in picture 1.",
    "right": "Side profile: plates close to the body, the power pack flat against the back (no bulk). Keep the feet and legs exactly where they are in picture 1.",
}
LOOKS = {
    "chrome": "a sleek modern robot suit: a polished chrome and white enamel chest plate with a round glowing blue core in the "
              "middle; a thin chrome collar ring around the base of the neck with a small antenna at the back; segmented chrome "
              "shoulder caps; white upper-arm and forearm plates; chrome mechanical mitten gauntlets with visible knuckle joints; "
              "a black flexible waist section; white thigh plates and chrome knee caps; white shin guards; heavy chrome robot "
              "boots; thin glowing blue light strips along the edges of the plates",
    "brass": "a Victorian clockwork automaton suit: a riveted polished brass chest plate with a small round glass window showing "
             "turning gears, and a big wind-up key sticking out of the back; a brass collar ring around the base of the neck; "
             "copper shoulder caps with rivets; brass upper-arm and forearm plates with leather straps; brass mechanical mitten "
             "gauntlets with hinged knuckles; a dark leather waist section; brass thigh plates and domed copper knee caps; brass "
             "shin guards; heavy riveted brass boots; a small pressure gauge on the chest",
    "canada": "a Canada Goose robot suit in the goose's own colours: a satin-finish chest plate in warm grey-brown with a cream "
              "lower belly plate and a round glowing amber core; a glossy black collar ring around the base of the neck with a "
              "white stripe; grey-brown shoulder caps with dark seams; grey-brown upper-arm and forearm plates; black mechanical "
              "mitten gauntlets with visible knuckle joints; a black flexible waist section; cream thigh plates and black knee "
              "caps; grey-brown shin guards; heavy black robot boots; thin glowing amber light strips along the plate edges",
}
for look, outfit in LOOKS.items():
    d = ROOT / "refs" / f"outfit_male_robot_{look}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "t2i_prompt.json").write_text(json.dumps({
        "note": f"Pete 2026-11-07: robot outfit for the geese (player bots' Canada Goose bot, Tandemonium #611); look '{look}'.",
        "outfit": outfit, "style": STYLE, "view_hint": HINT}, indent=1), encoding="utf-8")
    print("wrote", d / "t2i_prompt.json")
