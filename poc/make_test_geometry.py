"""検証用形状: 外箱(壁) + MRF円筒(完全内部) + MRF内のハブ(回転壁)"""
import sys

import trimesh

out = sys.argv[1]
trimesh.creation.box(extents=[0.4, 0.4, 0.6]).export(f"{out}/walls.stl")
trimesh.creation.cylinder(radius=0.1, height=0.15, sections=128).export(f"{out}/mrf.stl")
trimesh.creation.cylinder(radius=0.04, height=0.08, sections=64).export(f"{out}/hub.stl")
