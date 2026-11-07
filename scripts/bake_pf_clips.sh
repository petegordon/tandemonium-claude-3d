#!/usr/bin/env bash
# Penny-Farthing pedal clips (Tandemonium #611) for every in-game outfit:
#   bash scripts/bake_pf_clips.sh [chars...]          -> out/pf_tandem/clips/<char>_pf.glb (armature + clip "Pedal_PF")
# Needs out/bike/bike_rigged_pf.blend (make_pf_tandem.py) and out/<char>-goose/ (the dressed geese; in a worktree,
# junction them from the main checkout). Both halves of the Penny-Farthing are the same from the rider's seat, so one
# clip per outfit serves either seat: the captain plays it forward, the stoker plays it reversed (she faces backwards
# and the bike rolls the captain's way). Everyone rides like a captain here (own bars, own wheel in front), so each
# outfit uses the captain preset plus its lady / gent cloth settings from bake_riders.sh.
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
COMMON="--bike pf --max-bar-raise 0 --scales 1.0 --clips --clip-name Pedal_PF --pedal-only"
CAP="--seat Captain --side-lean 35 --hand-pitch 35 --elbow-out 0.3"
declare -A ARGS=(
  [outfit_male]="$CAP --follow S=1.0,B=0.15"
  [outfit_male_cyclist]="--dressed-tag full $CAP"
  [outfit_male_victorian]="--dressed-tag full $CAP --follow S=1.0,B=0.15"
  [outfit_male_georgian]="--dressed-tag full $CAP --follow S=1.0,B=0.15"
  [outfit_female]="$CAP --riding-hem 0.45,0.6,0.55 --hem-axis y --bustle 0.3"   # tighter than the tandem: the big wheel runs between the legs
  [outfit_female_cyclist]="--dressed-tag full $CAP --riding-hem 1,1,1"
  [outfit_female_victorian]="--dressed-tag full $CAP --riding-hem 0.45,0.6,0.55 --hem-axis y"
  [outfit_female_georgian]="--dressed-tag full $CAP --riding-hem 0.38,0.55,0.62 --hem-axis y"
)
NAMES="${*:-outfit_male outfit_male_cyclist outfit_male_victorian outfit_male_georgian outfit_female outfit_female_cyclist outfit_female_victorian outfit_female_georgian}"
mkdir -p renders/riders out/pf_tandem/clips
for c in $NAMES; do
  "$B" -b --factory-startup --python scripts/ride_fit.py -- --char "$c" ${ARGS[$c]} --tag pf $COMMON \
      --clip-pack "out/pf_tandem/clips/${c}_pf.glb" > "renders/riders/bake_pf_$c.log" 2>&1 \
    || { echo "FAILED $c"; tail -5 "renders/riders/bake_pf_$c.log"; exit 1; }
  echo "$c: $(grep -E '^FIT' "renders/riders/bake_pf_$c.log" | grep -oE '"leg_R": [0-9.]+'), $(grep -E '^CLIPS' "renders/riders/bake_pf_$c.log" | grep -oE '"contact_err_mm_max": [0-9.]+'), skirt in wheel: $(grep -E '^CLIPS' "renders/riders/bake_pf_$c.log" | grep -oE 'wheel": \[[^]]*\]' | tr -d ' ' | cut -c9-60)"
done
