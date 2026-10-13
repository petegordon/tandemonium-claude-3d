"""Colour-change review renders: every pair in refs/colourways.json in its own colours + each colourway, both geese,
3/4 view -> renders/colourways/<pair>_<way>_<seat>.png (scripts/colourway_sheet.py lays out the sheet).

  python -I scripts/colourway_renders.py [--jobs 4] [--only victorian]
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
argv = sys.argv[1:]
JOBS = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 4
ONLY = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
OUT = ROOT / "renders" / "colourways"
OUT.mkdir(parents=True, exist_ok=True)


def glb(ch):
    tag = "" if ch in ("outfit_male", "outfit_female") else "_full"
    return f"out/{ch}-goose/{ch}{tag}_dressed.glb"


W = json.loads((ROOT / "refs" / "colourways.json").read_text(encoding="utf-8"))
jobs = []
for pk, p in W["pairs"].items():
    if ONLY and pk not in ONLY:
        continue
    for way in ["default"] + list(p["ways"]):
        for seat in ("captain", "stoker"):
            cmd = [BLENDER, "-b", "--factory-startup", "--python", "scripts/outfit_beauty.py", "--", "--glb", glb(p[seat]),
                   "--out", f"renders/colourways/{pk}_{way}_{seat}.png", "--px", "760", "--floor", "0.6", "--views", "q34:30"]
            if way != "default":
                cmd += ["--recolour", f"refs/colourways.json:{way}:{seat}"]
            jobs.append(cmd)


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = "BEAUTY" in r.stdout
    print(("ok  " if ok else "FAIL"), cmd[9], cmd[cmd.index("--out") + 1], flush=True)
    if not ok:
        print(r.stdout[-1500:], r.stderr[-800:])
    return ok


with ThreadPoolExecutor(JOBS) as ex:
    res = list(ex.map(run, jobs))
print("RENDERS", sum(res), "/", len(res))
