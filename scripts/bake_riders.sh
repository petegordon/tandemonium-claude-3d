#!/usr/bin/env bash
# Riding clips for every in-game goose (Goose Outfits pairs), packed for the game:
#   bash scripts/bake_riders.sh [names...]      (default: all six)   -> out/delivery/goose_*.glb
# Captains first (each stoker's renders use its captain's fit scene as --base). Settings per rider are Pete's
# decisions (P5.4 / P5.7) plus the 2026-10-13 in-game review: per-chain drape, lengthwise riding hem (--hem-axis y),
# bustle folded for the Fancy lady, stoker elbows in (--elbow-out 0.35), coat sides follow the thighs (--follow).
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
PY=/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe
COMMON="--bike goosefit26 --max-bar-raise 0 --scales 1.0 --clips"
CAP="--seat Captain --side-lean 35 --hand-pitch 35 --elbow-out 0.3"
STO="--seat Stoker --side-lean 30 --elbow-out 0.35"
declare -A ARGS=(
  [goose_captain]="--char outfit_male $CAP --follow S=1.0,B=0.15 --tag hpC"
  [goose_captain_cyclist]="--char outfit_male_cyclist --dressed-tag full $CAP --tag rideC"
  [goose_captain_fancy]="--char outfit_male_victorian --dressed-tag full $CAP --follow S=1.0,B=0.15 --tag rideC"
  [goose_stoker_victorian]="--char outfit_female_victorian --dressed-tag full $STO --riding-hem 0.8,0.9,0.96 --hem-axis y --tag vicS --base out/bike/fit_outfit_male_Captain_hpC.blend"
  [goose_stoker_cyclist]="--char outfit_female_cyclist --dressed-tag full $STO --riding-hem 1,1,1 --tag rideS --base out/bike/fit_outfit_male_cyclist_Captain_rideC.blend"
  [goose_captain_georgian]="--char outfit_male_georgian --dressed-tag full $CAP --follow S=1.0,B=0.15 --tag geoC"
  [goose_stoker_georgian]="--char outfit_female_georgian --dressed-tag full $STO --riding-hem 0.38,0.55,0.62 --hem-axis y --tag geoS --base out/bike/fit_outfit_male_georgian_Captain_geoC.blend"
  [goose_stoker]="--char outfit_female $STO --riding-hem 0.72,0.84,0.94 --hem-axis y --bustle 0.3 --tag fancyS --base out/bike/fit_outfit_male_victorian_Captain_rideC.blend"
)
NAMES="${*:-goose_captain goose_captain_cyclist goose_captain_fancy goose_stoker_victorian goose_stoker_cyclist goose_stoker}"
mkdir -p renders/riders out/delivery
for n in $NAMES; do
  a=${ARGS[$n]}
  c=$(echo "$a" | sed -E 's/.*--char ([a-z_]+).*/\1/')
  "$B" -b --factory-startup --python scripts/ride_fit.py -- $a $COMMON > renders/riders/bake_$n.log 2>&1 \
    || { echo "FAILED $n"; tail -5 renders/riders/bake_$n.log; exit 1; }
  echo "$n: $(grep -E '^CLIPS' renders/riders/bake_$n.log | grep -oE '"contact_err_mm_max": [0-9.]+'), $(grep -E '^SEAMS|^LINING' renders/riders/bake_$n.log | tr '\n' ' ')"
  "$PY" -I scripts/glb_pack_images.py out/$c-goose/${c}_rider.glb out/delivery/$n.glb | sed 's/^/  /'
done
