#!/usr/bin/env bash
# The 18th-century frock coat (outfit_male_georgian), recipe to installed shells:
#   bash scripts/build_georgian_coat.sh
# coat = the body to the hips (make_garment kind coat) + coatskirt = the skirts sewn at the waist (make_skirt.py with
# "opening": cutaway front + back vent), gold braid on every open edge, standing collar, deep braided cuffs, gilt
# buttons down both fronts and on the cuffs, white lace ruffles at the wrists (make_cuffs.py -> shells/cuffs.glb).
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
C=outfit_male_georgian
run() { "$B" -b --factory-startup --python "$@" 2>&1 | grep -E "^(SHELL|PATTERN|PIPING|COLLAR|COAT CUFFS|BUTTONS|LINED|CUFFS)|Error|Traceback|line [0-9]+," | cut -c1-140 || true; }
run scripts/make_garment.py -- --char $C --piece coat
run scripts/make_cuffs.py -- --char $C --from coat          # (from the bare sleeve ends, before the cuff bands add loops)
run scripts/clean_normal.py -- --piece coat --char $C --max-tilt 12
run scripts/pattern_paint.py -- --char $C --piece coat
# gilt buttons down both front edges (x = the open half width + 1.5 cm), cast from the front
EX=""
for zw in 0.84:0.101 0.905:0.094 0.97:0.0855 1.035:0.083 1.10:0.08 1.165:0.0775 1.23:0.073; do
  z=${zw%%:*}; w=${zw##*:}; x=$(awk "BEGIN{print $w+0.016}")
  EX="$EX;$x,-0.4,$z;-$x,-0.4,$z"
done
run scripts/add_buttons.py -- --char $C --piece coat --extra-only --extra-ray --extra "${EX#;}" --extra-r 0.0105
run scripts/add_piping.py -- --char $C --piece coat --zmax 1.2 --r 0.0028 --skip-cuffs
run scripts/add_collar.py -- --char $C --piece coat --color 28,34,68
run scripts/add_coat_cuffs.py -- --char $C --piece coat --h 0.085 --ease 0.006 --repeat 3 --tex refs/outfit_male_georgian/prepped/cuff_texture.png --rim-color 206,160,70
run scripts/add_lining.py -- --char $C --piece coat --zmax 0.9 --inset 0.003 --color 22,26,52
run scripts/make_skirt.py -- --char $C --piece coatskirt
run scripts/pattern_paint.py -- --char $C --piece coatskirt
run scripts/add_piping.py -- --char $C --piece coatskirt --r 0.0028 --zmax 0.84
run scripts/add_lining.py -- --char $C --piece coatskirt --inset 0.003 --color 22,26,52
