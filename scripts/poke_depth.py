"""Body poke-through depth by region: base hi body vs an aligned outfit.
  blender -b --factory-startup --python scripts/poke_depth.py -- <base_hi.glb> <outfit_aligned.glb>
Signed by outfit face normals; inside double-walled skirts the sign can flip."""
import bpy, sys, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
a=sys.argv[sys.argv.index("--")+1:]
def load(p):
    b=set(bpy.context.scene.objects); bpy.ops.import_scene.gltf(filepath=p)
    o=[x for x in bpy.context.scene.objects if x not in b and x.type=="MESH"][0]
    o.select_set(True); bpy.context.view_layer.objects.active=o
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM"); bpy.ops.object.transform_apply(location=True,rotation=True,scale=True); return o
bpy.ops.wm.read_factory_settings(use_empty=True)
base=load(a[0]); out=load(a[1])
bv=BVHTree.FromObject(out,bpy.context.evaluated_depsgraph_get())
co=np.array([v.co[:] for v in base.data.vertices]); H=co[:,2].max()
rng=np.random.default_rng(0); co=co[rng.choice(len(co),30000,replace=False)]
co=co[co[:,2]<0.80*H]
d=[]
for p in co:
    l,n,_,_=bv.find_nearest(Vector(p)); v=p-np.array(l); d.append(np.linalg.norm(v)*np.sign(v@np.array(n)))
d=np.array(d)*1000
x=np.abs(co[:,0]); z=co[:,2]/H
regions={"feet z<.06":z<.06,"boots/shins .06-.25":(z>=.06)&(z<.25),"thighs/hips .25-.48":(z>=.25)&(z<.48)&(x<.15),
 "hands/forearms x>.15":x>=.15,"torso .48-.80":(z>=.48)&(x<.15)}
for k,m in regions.items():
    dd=d[m]; po=dd[dd>3]
    print("POKE",k,f"n={m.sum()} outside>3mm={len(po)/max(1,m.sum()):.0%} depth median={np.median(po) if len(po) else 0:.0f}mm p90={np.percentile(po,90) if len(po) else 0:.0f}mm max={po.max() if len(po) else 0:.0f}mm")
