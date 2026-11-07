#!/usr/bin/env bash
# Robot outfit (Tandemonium #611 player bots), whole chain:  CHAR=outfit_male_robot bash scripts/build_robot.sh
#   garments (make_garment + pattern_paint robotsuit / robotglove / robotplate) -> knee boots (make_boot) ->
#   hard parts (make_robot_parts: hat, collar, jacket, boot bands + knee caps) -> dress_goose -> review renders
set -e
cd "$(dirname "$0")/.."
B="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
C=${CHAR:-outfit_male_robot}
mkdir -p out/$C-goose/shells out/$C-goose/versions
CHAR=$C bash scripts/build_cyclist.sh breeches shirt waistcoat gloves
"$B" -b --factory-startup --python scripts/make_boot.py -- --char $C --tris 4500 2>&1 | grep -E "^BOOT|Error" || true
"$B" -b --factory-startup --python scripts/make_robot_parts.py -- --char $C 2>&1 | grep -E "^(PART|CAP)|Error" || true
"$B" -b --factory-startup --python scripts/dress_goose.py -- --char $C --tag full 2>&1 | grep -E "^RENDER|RIGID_PART|Error" || true
CHAR=$C RDIR=renders/robot bash scripts/review_cyclist.sh ${TAG:-latest}
