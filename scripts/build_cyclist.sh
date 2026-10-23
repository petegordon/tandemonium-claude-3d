#!/usr/bin/env bash
# Build the 1920s cyclist's garments on the base goose (chars/outfit_male_cyclist.json), piece by piece:
#   bash scripts/build_cyclist.sh breeches shirt waistcoat ...   (no args = all, in layering order)
# Each designed garment: make_garment.py -> clean_normal.py -> pattern_paint.py (when the recipe has a pattern).
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
PY=/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe
C=${CHAR:-outfit_male_cyclist}           # (CHAR=outfit_female_cyclist bash scripts/build_cyclist.sh ...)
run() { "$B" -b --factory-startup --python "$@" 2>&1 | grep -E "^(CROP|SHELL|CLEAN|PATTERN|BAND|HAT|CAP|BOOT|STRAP|RENDER|TARGET|BUCKLES|BOWS|FOB|BRACES|KNOT)|Error|Traceback|line [0-9]+," || true; }
has_pattern() { "$PY" -I -c "import json,sys;d=json.load(open('chars/$C.json',encoding='utf-8'));sys.exit(0 if '$1' in d.get('patterns',{}) else 1)"; }
PIECES="${*:-breeches shirt waistcoat gloves socks}"
for p in $PIECES; do
  echo "== $p"
  case $p in
    boots) run scripts/make_boot.py -- --char $C ;;
    hat) if grep -q '"mobcap_design"' chars/$C.json; then run scripts/make_mobcap.py -- --char $C
         elif grep -q '"cloche_design"' chars/$C.json; then run scripts/make_cloche.py -- --char $C
         elif grep -q '"hat_design"' chars/$C.json; then run scripts/make_hat.py -- --char $C
         else run scripts/make_cap.py -- --char $C; fi ;;
    skirt|petticoat|coatskirt|apron|apronband|shawl) run scripts/make_skirt.py -- --char $C --piece $p ;;
    pancollar) run scripts/make_accessory.py -- --char $C --piece pancollar ;;
    necktie) run scripts/make_accessory.py -- --char $C --piece necktie ;;
    bowtie) run scripts/make_accessory.py -- --char $C --piece bowtie ;;
    jabot|fichu) run scripts/make_jabot.py -- --char $C --piece $p ;;
    *) run scripts/make_garment.py -- --char $C --piece $p
       RF=$("$PY" -I -c "import json;print(int(bool(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p'].get('relax_folds'))))")
       if [ "$RF" = 1 ]; then "$B" -b --factory-startup --python scripts/relax_folds.py -- --piece $p --char $C 2>&1 | grep -iE "crease|Error" || true; fi
       NT=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p'].get('normal_tilt',18))")
       run scripts/clean_normal.py -- --piece $p --char $C --max-tilt $NT
       TB=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p'].get('trim_below',''))")
       if [ -n "$TB" ]; then run scripts/trim_edge.py -- --char $C --piece $p --z $TB --below; fi ;;
  esac
  if has_pattern $p; then run scripts/pattern_paint.py -- --char $C --piece $p; fi
  if [ "$p" = breeches ] && grep -q '"kneestrap"' chars/$C.json; then run scripts/add_kneestrap.py -- --char $C; fi
  for TK in fob braces; do           # modelled trims joined into this shell (add_trims.py), when the recipe has them
    if grep -q "\"$TK\"" chars/$C.json && [ "$("$PY" -I -c "import json;d=json.load(open('chars/$C.json',encoding='utf-8'));print(d['$TK'].get('piece','waistcoat' if '$TK'=='fob' else 'breeches'))" | tr -d '[:space:]')" = "$p" ]; then run scripts/add_trims.py -- --char $C --kind $TK; fi
  done
  if grep -q '"shawl_knot"' chars/$C.json && [ "$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['shawl_knot'].get('piece','shawl'))" | tr -d '[:space:]')" = "$p" ]; then run scripts/add_shawl_knot.py -- --char $C; fi
  if grep -q '"bow_trims"' chars/$C.json && "$PY" -I -c "import json,sys;b=json.load(open('chars/$C.json',encoding='utf-8'))['bow_trims'];sys.exit(0 if '$p' in [x.get('piece','jacket') for x in (b if isinstance(b,list) else [b])] else 1)"; then run scripts/add_bows.py -- --char $C --piece $p; fi
  if [ "$p" = boots ] && grep -q '"shoe_buckle"' chars/$C.json; then run scripts/add_shoe_buckle.py -- --char $C; fi
  WT=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design'].get('$p',{}).get('with_outfit',{}).get('trim_below',''))" 2>/dev/null)
  if [ -n "$WT" ]; then      # worn under another garment in the full outfit: the hidden lower part cut away
    V=out/$C-goose/shells/variants/withshoes; mkdir -p $V
    cp out/$C-goose/shells/$p.glb out/$C-goose/shells/$p.json out/$C-goose/shells/${p}_weights.npz out/$C-goose/shells/${p}_covers.npz $V/
    run scripts/trim_edge.py -- --char $C --piece $p --z $WT --below --glb shells/variants/withshoes/$p.glb --out shells/variants/withshoes/$p.glb
    WB=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p']['with_outfit'].get('keep_box',''))")
    WC=$("$PY" -I -c "import json;print('--bisect' if json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['$p']['with_outfit'].get('bisect') else '')")
    if [ -n "$WB" ]; then run scripts/crop_shell.py -- --char $C --glb shells/variants/withshoes/$p.glb --box $WB $WC; fi
  fi
  if [ "$p" = socks ]; then           # the with-shoes variant: foot trimmed inside the shoe (dress_goose.py --variant withshoes)
    V=out/$C-goose/shells/variants/withshoes; mkdir -p $V
    cp out/$C-goose/shells/socks.glb out/$C-goose/shells/socks.json out/$C-goose/shells/socks_weights.npz out/$C-goose/shells/socks_covers.npz $V/
    TZ=$("$PY" -I -c "import json;print(json.load(open('chars/$C.json',encoding='utf-8'))['garment_design']['socks'].get('with_shoes',{}).get('trim_below',0.075))")
    run scripts/trim_edge.py -- --char $C --piece socks --z $TZ --below --glb shells/variants/withshoes/socks.glb --out shells/variants/withshoes/socks.glb
  fi
done
