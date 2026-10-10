# Tandemonium — v3 reconstruction references

The original PNG is saved byte-for-byte as source-reference.png. Its SHA-256 and the saved image hashes are in manifest.json.

## Sheets and panel order

| Sheet | PNG size | Top row | Bottom row |
| --- | --- | --- | --- |
| mannequin-turnaround.png | 1024 x 1536 | FRONT, LEFT profile | REAR, RIGHT profile |
| male-character-turnaround.png | 1024 x 1536 | FRONT, LEFT profile | REAR, RIGHT profile |
| female-character-turnaround.png | 1024 x 1536 | FRONT, LEFT profile | REAR, RIGHT profile |
| bicycle-turnaround.png | 1536 x 1024 | LEFT side, RIGHT side | FRONT, REAR |

Only the four reconstruction sheets are included. No seated/alternative pose sheet or assembly sheet is mixed into these inputs.

## Shared body and fixed pose

One sex-neutral fully feathered Canada goose design guides all three goose sheets. The clothed sheets used the corrected mannequin as the body and pose reference and the original illustration as the costume reference.

Requested fixed pose: standing upright, level forward-facing head, feet flat and hip-width apart, straight arms spread 30 degrees sideways from vertical, hands open with palms inward. No forward reach or elbow bend. In profile the lateral spread is foreshortened, so the near arm projects vertically and the hand lies beside the hip; the far arm is occluded.

Male outfit: brown bowler, chestnut jacket, tan waistcoat/trousers, ivory shirt, black bow tie/gloves and tall boots. Female outfit: burgundy rosette/plume hat, full-length puff-and-fitted sleeves, burgundy dress with rear bustle and layered hem, black gloves and boots. The plume and bustle were requested as fixed accessories viewed from four directions.

## Bicycle

An 1890s black-and-brass inline tandem with two spoked wheels, mudguards, front brass headlamp, rear rack, two brown sprung saddles, two handlebar assemblies, two cranksets and four pedals. Front handlebar on fork stem; rear handlebar references front rider seatpost. Left timing chain joins cranks; right drive chain joins rear crank to rear hub. Axial views align along one centerline.

## Review and corrections

The initial mannequin arm spread was rejected. Front/rear arms were spread outward and profile hand depth/height corrected to eliminate forward-reaching forearms. That corrected sheet guided both costume sheets. The female profile hand and plume clearance were refined. The bicycle left chain to rear hub was removed and enlarged axial views reduced. Final PNG sizes and source/copy hashes were verified.

## Reconstruction limitation

These are generated orthographic-style images, not four renders from one fixed 3D mesh. Exact joint coordinates, accessory geometry, identical magnification and equal panel registration cannot be certified from generated artwork. Small residual differences remain; bicycle axial/profile height registration and generated panel-divider positions are approximate. This set is not calibrated multi-view ground truth and cannot guarantee artifact-free image-to-3D reconstruction.

For mathematically identical geometry, render one fixed goose mesh/pose with both clothing sets and one fixed bicycle mesh using orthographic cameras at 90-degree increments. That modeling/rendering step is not included in this image set.

Use the panel labels and check actual divider locations when extracting views rather than assuming every generated divider is at the exact midpoint. PROMPTS.md records every generation/edit prompt, including unsuccessful corrections. Rejected draft images remain outside this directory.

Generator: built-in image_gen tool.

