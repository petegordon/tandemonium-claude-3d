#!/usr/bin/env bash
# Each garment on its own on the naked base goose, rigged and skinned (dress_goose.py --without every other piece):
#   bash scripts/dress_singles.sh [char]   -> out/<char>-goose/<char>_only_<piece>_dressed.glb
#                                             + renders/cyclist/singles_<piece>.png (front, 3/4, side, rear)
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
C=${1:-outfit_male_cyclist}
PIECES=$(ls out/$C-goose/shells/*.glb | xargs -n1 basename | sed 's/\.glb$//' | grep -v '@')
RD=renders/cyclist; [ "$C" != outfit_male_cyclist ] && RD=renders/cyclist/$C; mkdir -p $RD
for p in $PIECES; do
  others=$(echo $PIECES | tr ' ' '\n' | grep -vx "$p" | paste -sd, -)
  "$B" -b --factory-startup --python scripts/dress_goose.py -- --char $C --tag only_$p --without "$others" --no-poses \
    > $RD/dress_only_$p.log 2>&1 || { echo "FAILED $p"; tail -5 $RD/dress_only_$p.log; continue; }
  "$B" -b --factory-startup --python scripts/outfit_beauty.py -- --glb out/$C-goose/${C}_only_${p}_dressed.glb \
    --out $RD/singles_$p.png --px 700 --floor 0.6 --views front:0,q34:35,side:90,rear:180 2>&1 | grep -E "Error" || true
  echo "ONLY $p -> out/$C-goose/${C}_only_${p}_dressed.glb"
done
