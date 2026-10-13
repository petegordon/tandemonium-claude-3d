# Jacket (coat) of the Victorian male outfit, recipe to installed shell -- the round-6 chain:
#   bash scripts/build_victorian_coat.sh <tag>
# built over the SLIM shirt (shells/variants/jacket), armpits relaxed clear of shirt + vest, baked from the drawings
# (painted buttons erased first: erase_ref_buttons.py), flattened cloth + weave tile, plain sleeves (--tile-near), lapel
# brocade painted (--lapel), 12 brass buttons, flattened normal map, gold piping, standing collar, brocade cuffs over the
# glove gauntlets, gold-piped back tab with two buttons, brown lining.
cd "$(dirname "$0")/.."
B="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"; D=out/outfit_male_victorian-goose; T=$1
cp $D/shells/shirt.glb $D/versions/_shirt_bishop.glb
cp $D/shells/variants/jacket/shirt.glb $D/shells/shirt.glb
"$B" -b --factory-startup --python scripts/make_garment.py -- --char outfit_male_victorian --piece coat 2>&1 | grep -E "Traceback"
cp $D/versions/_shirt_bishop.glb $D/shells/shirt.glb
cp $D/shells/coat.glb $D/versions/coat_built_$T.glb
"$B" -b --factory-startup --python scripts/relax_folds.py -- --piece coat --zmin 0.95 --over shirt,waistcoat --variant jacket --over-clear 0.006 --push-all --grow 3 --rounds 3 --iters 120 --spheres "0.14,0.03,1.1,0.1;-0.14,0.03,1.1,0.1" 2>&1 | grep -E "Traceback|RELAX" | cut -c1-80
"$B" -b --factory-startup --python scripts/project_bake.py -- --piece coat --tag $T --lift 0.75 --speck 0.45 --flatten 0.9 --cloth-tile 12 --tile-near "0.154,0.005,1.145,0.09;0.197,0.009,1.081,0.09;0.240,0.013,1.017,0.09;0.284,0.012,0.954,0.1;0.320,0.009,0.901,0.1;0.349,0.007,0.858,0.1;0.377,0.005,0.816,0.1;-0.154,0.005,1.145,0.09;-0.197,0.009,1.081,0.09;-0.240,0.013,1.017,0.09;-0.284,0.012,0.954,0.1;-0.320,0.009,0.901,0.1;-0.349,0.007,0.858,0.1;-0.377,0.005,0.816,0.1;0.15,-0.09,1.18,0.05;-0.15,-0.09,1.18,0.05;0.26,0.04,0.8,0.06;-0.26,0.04,0.8,0.06;0.24,0.02,0.93,0.045;-0.24,0.02,0.93,0.045" --lapel "0.99,1.25,0.035,0.10,0.0,0.06,refs/outfit_male_victorian/jacket/prepped/lapel_texture.png" 2>&1 | grep -E "Traceback|GOLD|CLOTH TILE" | cut -c1-80
EX="0.078,-0.4,0.975;-0.078,-0.4,0.975;0.114,-0.4,0.975;-0.114,-0.4,0.975;0.093,-0.4,0.935;-0.093,-0.4,0.935;0.129,-0.4,0.935;-0.129,-0.4,0.935;0.107,-0.4,0.895;-0.107,-0.4,0.895;0.143,-0.4,0.895;-0.143,-0.4,0.895"
"$B" -b --factory-startup --python scripts/add_buttons.py -- --piece coat --extra-only --extra-ray --extra "$EX" --extra-r 0.017 2>&1 | grep -E "Traceback|BUTTONS" | cut -c1-50
"$B" -b --factory-startup --python scripts/clean_normal.py -- --piece coat --max-tilt 12 2>&1 | grep -E "Traceback"
"$B" -b --factory-startup --python scripts/add_piping.py -- --piece coat --zmax 1.2 2>&1 | grep -E "Traceback|PIPING"
"$B" -b --factory-startup --python scripts/add_collar.py -- --piece coat --color 90,28,32 2>&1 | grep -E "Traceback|Error|COLLAR|no neckline"
"$B" -b --factory-startup --python scripts/add_back_tab.py -- --piece coat 2>&1 | grep -E "Traceback|Error|BACK TAB"
"$B" -b --factory-startup --python scripts/add_coat_cuffs.py -- --piece coat --over gloves 2>&1 | grep -E "Traceback|Error|COAT CUFFS"
"$B" -b --factory-startup --python scripts/add_lining.py -- --piece coat --zmax 0.9 --inset 0.003 2>&1 | grep -E "Traceback|LINED"
cp $D/shells/coat.glb $D/versions/coat_${T}_installed.glb
