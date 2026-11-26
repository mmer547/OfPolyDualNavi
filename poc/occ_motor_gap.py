"""ギャップ押し出し方式のためのテトラ生成 (ルートA + ギャップ除外)

部品STEPから流体を作り、エアギャップの円環 (ロータ外径〜ステータ内径, コア長の範囲) を
Netgen の領域から除外する。ギャップ両端の円環面は「周期境界」として同一の三角形分割にし、
MRF界面の円で内側(R)/外側(S)の2面に分ける。デュアル化後、下端の円環面を軸方向に
押し出してギャップを埋め、上下とも stitchMesh -perfect で縫い合わせる (AMI 不要)。

円環面のパッチ名: gapLoR, gapLoS (下端), gapHiR, gapHiS (上端)  R=界面より内側, S=外側

例:
  python occ_motor_gap.py out --cavity housing.step --solid statorCore.step --solid rotorCore.step \
     --solid shaft.step --mrf 0,0,-0.045:0,0,1:0.041:0.09 --gap 0.040:0.042:-0.04:0.04 \
     --maxh 0.008 --gap-h 0.0005 --local-h rotorCore:0.0015 --local-h statorCore:0.0015
"""
import argparse
import collections
import math
import os
import time

from netgen.occ import Cylinder, Glue, IdentificationType, OCCGeometry, Pnt, Z, gp_Trsf, gp_Vec

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
    ap.add_argument("--mrf", required=True, help="ox,oy,oz:ax,ay,az:R:L (軸はZ方向を想定)")
    ap.add_argument("--gap", required=True, help="Rr:Rs:z0:z1 (ロータ外径半径:ステータ内径半径:コア下端:上端)")
    ap.add_argument("--maxh", type=float, required=True)
    ap.add_argument("--gap-h", type=float, required=True, help="ギャップ両端の円環面の maxh (=半径方向の分割)")
    ap.add_argument("--gap-edge-h", type=float, default=None, help="円環の壁側の円(ロータ外径/ステータ内径)の maxh")
    ap.add_argument("--grading", type=float, default=0.3)
    ap.add_argument("--local-h", action="append", default=[], help="patch:maxh")
    a = ap.parse_args()

    stem = lambda p: os.path.splitext(os.path.basename(p))[0]
    fluid = load(a.cavity, stem(a.cavity))
    for p in a.solid:
        fluid = fluid - load(p, stem(p))
    Rr, Rs, z0, z1 = map(float, a.gap.split(":"))
    gap = Cylinder(Pnt(0, 0, z0), Z, r=Rs, h=z1 - z0) - Cylinder(Pnt(0, 0, z0), Z, r=Rr, h=z1 - z0)
    gap.faces.name = "gapRing"
    fluid = fluid - gap

    o, ax, R, L = a.mrf.split(":")
    o = list(map(float, o.split(","))); ax = list(map(float, ax.split(",")))
    Rm = float(R)
    cyl = Cylinder(Pnt(*o), gp_Vec(*ax), r=Rm, h=float(L))
    cyl.faces.name = "mrfInterface"
    rot = fluid * cyl
    sta = fluid - cyl
    rot.mat("MRF_rotor"); sta.mat("stator")
    shape = Glue([sta, rot])

    # ギャップ両端の円環面を分類して命名し、上下を周期境界で対応づける
    tol = 1e-6
    ring = {}
    for f in shape.faces:
        bb = f.bounding_box
        zmin, zmax = bb[0][2], bb[1][2]
        rmax = max(abs(bb[0][0]), abs(bb[1][0]), abs(bb[0][1]), abs(bb[1][1]))
        if abs(zmax - zmin) > tol:
            continue
        side = "Lo" if abs(zmin - z0) < tol else "Hi" if abs(zmin - z1) < tol else None
        if side is None:
            continue
        half = "R" if abs(rmax - Rm) < 1e-5 else "S" if abs(rmax - Rs) < 1e-5 else None
        if half is None:
            continue
        f.name = f"gap{side}{half}"
        f.maxh = a.gap_h
        if a.gap_edge_h:   # 壁側の円の辺を細かくして、ギャップ内の壁近傍を解像する
            for e in f.edges:
                eb = e.bounding_box
                er = max(abs(eb[0][0]), abs(eb[1][0]))
                if abs(er - Rr) < 1e-5 or abs(er - Rs) < 1e-5:
                    e.maxh = a.gap_edge_h
        ring[side + half] = f
    assert set(ring) == {"LoR", "LoS", "HiR", "HiS"}, f"円環面の検出に失敗: {sorted(ring)}"
    trafo = gp_Trsf.Translation(gp_Vec(0, 0, z1 - z0))
    for half in "RS":
        ring["Lo" + half].Identify(ring["Hi" + half], f"gap{half}", IdentificationType.PERIODIC, trafo)

    lh = dict(x.split(":") for x in a.local_h)
    for f in shape.faces:
        if f.name in lh:
            f.maxh = float(lh[f.name])
    t = time.time()
    m = OCCGeometry(shape).GenerateMesh(maxh=a.maxh, grading=a.grading)
    print(f"netgen: {time.time()-t:.1f}s")

    tags, fd2tag = {}, {}
    for i, fd in enumerate(m.FaceDescriptors()):
        name = "mrfInterface" if (fd.domin > 0 and fd.domout > 0) else fd.bcname
        fd2tag[i + 1] = tags.setdefault(name, len(tags) + 1)
    zones = {i + 1: m.GetMaterial(i + 1) for i in range(m.GetNDomains())}
    cnt = collections.Counter(e.index for e in m.Elements3D())
    nring = collections.Counter(m.FaceDescriptors()[e.index - 1].bcname for e in m.Elements2D()
                                if m.FaceDescriptors()[e.index - 1].bcname.startswith("gap"))
    print("tets per domain:", {zones[k]: v for k, v in cnt.items()}, "points:", len(m.Points()))
    print("ring triangles:", dict(nring))
    write_msh22(m, os.path.join(a.outdir, "tet.msh"), {v: k for k, v in tags.items()}, zones, fd2tag)


if __name__ == "__main__":
    main()
