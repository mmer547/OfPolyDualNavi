"""ルートA: 部品STEP + MRF円筒(解析形状) -> netgen.occ で界面一致の多領域テトラ

流体 = 空洞 - 固体部品。MRF円筒で 流体を MRF_rotor/stator 領域に分け、Glue で
界面を共有させる。パッチ名は部品名 (STEPファイル名) がそのまま引き継がれる。
MRF円筒が壁と交差しても、交線は OCC が刻むので問題にならない。

例:
  python occ_multidomain.py out --cavity housing.step --solid statorCore.step --solid rotorCore.step \
     --solid shaft.step --mrf 0,0,-0.045:0,0,1:0.041:0.09 --maxh 0.008 \
     --local-h rotorCore:0.0007 --local-h statorCore:0.0007 --local-h mrfInterface:0.0015
"""
import argparse
import collections
import os
import time

from netgen.occ import Cylinder, Glue, OCCGeometry, Pnt, gp_Vec

from ng2msh import write_msh22


def load(path, name):
    s = OCCGeometry(path).shape
    s.faces.name = name
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--cavity", required=True)
    ap.add_argument("--solid", action="append", default=[])
    ap.add_argument("--mrf", required=True, help="ox,oy,oz:ax,ay,az:R:L (原点は円筒の端面中心)")
    ap.add_argument("--maxh", type=float, required=True)
    ap.add_argument("--grading", type=float, default=0.3)
    ap.add_argument("--local-h", action="append", default=[], help="patch:maxh")
    a = ap.parse_args()

    stem = lambda p: os.path.splitext(os.path.basename(p))[0]
    fluid = load(a.cavity, stem(a.cavity))
    for p in a.solid:
        fluid = fluid - load(p, stem(p))
    o, ax, R, L = a.mrf.split(":")
    o = list(map(float, o.split(","))); ax = list(map(float, ax.split(",")))
    cyl = Cylinder(Pnt(*o), gp_Vec(*ax), r=float(R), h=float(L))
    cyl.faces.name = "mrfInterface"
    rot = fluid * cyl
    sta = fluid - cyl
    rot.mat("MRF_rotor"); sta.mat("stator")
    shape = Glue([sta, rot])
    lh = dict(x.split(":") for x in a.local_h)
    for f in shape.faces:
        if f.name in lh:
            f.maxh = float(lh[f.name])
    t = time.time()
    m = OCCGeometry(shape).GenerateMesh(maxh=a.maxh, grading=a.grading)
    print(f"netgen: {time.time()-t:.1f}s")
    # FaceDescriptor -> 名前 (同名は1つの物理タグにまとめる)
    tags, fd2tag = {}, {}
    for i, fd in enumerate(m.FaceDescriptors()):
        name = fd.bcname
        if fd.domin > 0 and fd.domout > 0:
            name = "mrfInterface"          # 領域間の面は必ず界面として扱う
        fd2tag[i + 1] = tags.setdefault(name, len(tags) + 1)
    zones = {i + 1: m.GetMaterial(i + 1) for i in range(m.GetNDomains())}
    cnt = collections.Counter(e.index for e in m.Elements3D())
    print("tets per domain:", {zones[k]: v for k, v in cnt.items()}, "points:", len(m.Points()),
          "patches:", list(tags))
    write_msh22(m, os.path.join(a.outdir, "tet.msh"), {v: k for k, v in tags.items()}, zones, fd2tag)


if __name__ == "__main__":
    main()
