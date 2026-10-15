#!/usr/bin/env bash
# Goose Studio body clips for every in-game goose (same pairs as bake_riders.sh):
#   bash scripts/bake_show.sh [names...] [-- extra show_clips.py args]  -> out/show/<name>_clips.glb + .json
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
declare -A ARGS=(
  [goose_captain]="--char outfit_male"
  [goose_captain_cyclist]="--char outfit_male_cyclist --dressed-tag full"
  [goose_captain_fancy]="--char outfit_male_victorian --dressed-tag full"
  [goose_stoker_victorian]="--char outfit_female_victorian --dressed-tag full"
  [goose_stoker_cyclist]="--char outfit_female_cyclist --dressed-tag full"
  [goose_stoker]="--char outfit_female"
)
NAMES=(); EXTRA=()
while [ $# -gt 0 ]; do [ "$1" = "--" ] && { shift; EXTRA=("$@"); break; }; NAMES+=("$1"); shift; done
[ ${#NAMES[@]} -eq 0 ] && NAMES=(goose_captain goose_captain_cyclist goose_captain_fancy goose_stoker_victorian goose_stoker_cyclist goose_stoker)
mkdir -p renders/show
for n in "${NAMES[@]}"; do
  "$B" -b --factory-startup --python scripts/show_clips.py -- ${ARGS[$n]} --name $n "${EXTRA[@]}" > renders/show/bake_$n.log 2>&1 \
    || { echo "FAILED $n"; tail -5 renders/show/bake_$n.log; exit 1; }
  echo "$n: $(grep -c '^CLIP' renders/show/bake_$n.log) clips, max reach $(grep -oE '"max_reach": [0-9.]+' renders/show/bake_$n.log | awk '{print $2}' | sort -n | tail -1)"
done
