#!/usr/bin/env bash
# Build the 1920s cyclist's garments on the base goose (chars/outfit_male_cyclist.json), piece by piece:
#   bash scripts/build_cyclist.sh breeches shirt waistcoat ...   (no args = all, in layering order)
# Each designed garment: make_garment.py -> clean_normal.py -> pattern_paint.py (when the recipe has a pattern).
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
PY=/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe
C=outfit_male_cyclist
run() { "$B" -b --factory-startup --python "$@" 2>&1 | grep -E "^(SHELL|CLEAN|PATTERN|BAND|HAT|CAP|BOOT|STRAP|RENDER|TARGET)|Error|Traceback|line [0-9]+," || true; }
has_pattern() { "$PY" -I -c "import json,sys;d=json.load(open('chars/$C.json',encoding='utf-8'));sys.exit(0 if '$1' in d.get('patterns',{}) else 1)"; }
PIECES="${*:-breeches shirt waistcoat gloves socks}"
for p in $PIECES; do
  echo "== $p"
  case $p in
    boots) run scripts/make_boot.py -- --char $C ;;
    hat) run scripts/make_cap.py -- --char $C ;;
    necktie) run scripts/make_accessory.py -- --char $C --piece necktie ;;
    *) run scripts/make_garment.py -- --char $C --piece $p
       NT=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p'].get('normal_tilt',18))")
       run scripts/clean_normal.py -- --piece $p --char $C --max-tilt $NT
       TB=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p'].get('trim_below',''))")
       if [ -n "$TB" ]; then run scripts/trim_edge.py -- --char $C --piece $p --z $TB --below; fi ;;
  esac
  if has_pattern $p; then run scripts/pattern_paint.py -- --char $C --piece $p; fi
  if [ "$p" = breeches ]; then run scripts/add_kneestrap.py -- --char $C; fi
  if [ "$p" = socks ]; then           # the with-shoes variant: foot trimmed inside the shoe (dress_goose.py --variant withshoes)
    V=out/$C-goose/shells/variants/withshoes; mkdir -p $V
    cp out/$C-goose/shells/socks.glb out/$C-goose/shells/socks.json out/$C-goose/shells/socks_weights.npz out/$C-goose/shells/socks_covers.npz $V/
    run scripts/trim_edge.py -- --char $C --piece socks --z 0.075 --below --glb shells/variants/withshoes/socks.glb --out shells/variants/withshoes/socks.glb
  fi
done
