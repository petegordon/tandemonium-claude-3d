#!/usr/bin/env bash
# Review renders of the dressed cyclist: key-camera views next to the reference + close-ups + the beauty sheet.
#   bash scripts/review_cyclist.sh <tag>        (dress_goose.py --char outfit_male_cyclist --tag full must have run)
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
PY=/c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe
T=${1:-v1}
G=out/outfit_male_cyclist-goose/outfit_male_cyclist_full_dressed.glb
R=renders/cyclist
mkdir -p $R
ob() { "$B" -b --factory-startup --python scripts/outfit_beauty.py -- --glb $G --floor 0.6 "$@" 2>&1 | grep -E "BEAUTY|Error" || true; }
ob --out $R/key_$T.png --views front:0,left:90,rear:180 --cams refs/key_views/cameras.json
ob --out $R/beauty_$T.png --px 1100
# close-ups (heights are on the dressed goose: legs x1.15 from the hips down)
ob --out $R/closeA_$T.png --px 800 --frame 1.45,0.55 --views front:0,q34:35,side:90,rear:180
ob --out $R/closeB_$T.png --px 800 --frame 0.75,0.75 --views front:0,q34:35,side:90,rear:180
ob --out $R/closeC_$T.png --px 800 --frame 0.22,0.42 --views front:0,q34:35,side:90,rear:180
"$PY" -I scripts/review_pack.py --ref refs/outfit_male_cyclist/t2i/key1 --ours "$R/_key_${T}_{view}.png" --out $R/review_$T.png
echo "renders: $R/review_$T.png $R/beauty_$T.png $R/closeA_$T.png $R/closeB_$T.png $R/closeC_$T.png"
