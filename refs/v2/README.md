# Tandemonium — reference set v2

New images generated from source-reference.png using the built-in image_gen tool. This set introduces ONE shared unclothed goose mannequin for both costumes. "Male" and "female" refer to the clothing sets applied to that same base character. There are no separate sex-specific body designs.

## Sheets and panel order

| File | Panel layout |
| --- | --- |
| mannequin-turnaround.png | 3 columns x 2 rows: front, left, right; rear, top, three-quarter. Relaxed standing pose. |
| mannequin-poses.png | 4 columns x 3 rows. Row 1 T-pose; row 2 A-pose; row 3 seated riding. Each row: front, left, rear, three-quarter. |
| male-character-turnaround.png | 3 columns x 2 rows: standing front, left, rear; T-pose front, A-pose front, seated riding three-quarter. |
| female-character-turnaround.png | Same pose coverage as male sheet. Full-length sleeves and black gloves were corrected to follow the original costume. |
| bicycle-turnaround.png | Top row: left and right side. Bottom row: front, rear, top, drivetrain close-up. These panels are not text-labeled in the generated sheet. |
| assembly-turnaround.png | 3 columns x 2 rows: left, right, front; rear, top, three-quarter. Male front rider and female rear rider in single file. |
| source-reference.png | Unmodified original illustration supplied for this request. |

## Shared body specification

Anthropomorphic Canada goose: long black neck, dark tapered bill, amber eyes, cream cheek patches, gray-brown feathered arms/back/thighs and a cream feathered underside. Feathered biped torso and arms have recognizable shoulder, elbow, wrist, hip and knee articulation. Dexterous avian hands can grip handlebars and fit gloves. Dark lower legs and webbed feet are inferred under the original costume; footwear in this set is adapted to that body. One compact rear feather tail.

The unclothed reference is a fully feathered avian body, without human skin, sexual anatomy, clothes or accessories. The mannequin is the primary BODY proportion reference; source-reference.png remains the original COSTUME and overall design authority.

## Intended modeling and rigging workflow

1. Build one clean base mesh from the standing and T/A-pose mannequin views. Reconcile view differences against one chosen front and profile proportion pair.
2. Establish one skeleton and bind the base body. Choose the T-pose or A-pose as the bind pose, not both.
3. Fit separate male and female clothing meshes to duplicates of the same base. Keep jackets, waistcoat, trousers, dress, gloves, boots and hats as separate assets as useful.
4. Allow clearance over the feather envelope and at shoulder, elbow, hip and knee bends. Resolve the tail/bustle interaction explicitly.
5. Share skeleton proportions and garment skinning conventions between clothing sets. Seated panels are deformation and garment-drape targets rather than new body geometries.
6. Build the bicycle separately. Both wheels, saddles and riders align along one longitudinal centerline. Use the assembly sheet for hand, saddle and pedal contact targets.

## Limits

These are AI-generated design references. Hidden body anatomy and back surfaces are inferred from one illustration. They are not calibrated orthographic scans, guaranteed exact pose projections, UV maps, topology guides, skeletal rigs, animation frames or ready-made clothing meshes. Small proportional, feather, hand, garment and bicycle/drivetrain differences can remain across panels. Resolve them in the 3D asset rather than trying to fit every image simultaneously. No physical dimensions are implied.

## Generation

See PROMPTS.md for every final generation and corrective edit prompt. The old reference set and male-goose 3D model were not used as design inputs for these new sheets.

