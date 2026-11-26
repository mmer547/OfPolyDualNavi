"""STL群から、MRF界面が一致した多領域テトラメッシュを Netgen で作る (PoC)

各STLを Netgen STL モジュールで個別に表面メッシュ化し、FaceDescriptor の
domin/domout で「どの領域とどの領域の間の面か」を指定して 1 つのメッシュに
組み立て、体積メッシュを生成する。

  domin  : 面の法線の「裏側」(=STLの内側) の領域番号
  domout : 法線の「表側」(=STLの外側) の領域番号   (0 = 計算領域外)

例 (外箱の壁, MRF円筒, MRF内のハブ):
  python netgen_multidomain.py out \
      --part walls.stl:0.03:1:0:walls \
      --part mrf.stl:0.012:2:1:mrfInterface \
      --part hub.stl:0.008:0:2:hub \
      --zone 1:stator --zone 2:rotor --maxh 0.03

制約: 各STLは閉じた多様体であること。MRF円筒が壁と交差/接触するケース
(結合すると非多様体になる) は Netgen STL モジュールが失敗する (検証済)。
その場合は docs/design.md の「ルートC」を参照。
"""
import argparse
import collections
import os

from netgen.meshing import Element2D, FaceDescriptor, Mesh, MeshingStep, MeshPoint, Pnt
from netgen.stl import STLGeometry

from ng2msh import write_msh22


def build(parts, zones, maxh):
    m = Mesh(dim=3)
    names = {}
    for stl, h, din, dout, name in parts:
        s = STLGeometry(stl).GenerateMesh(maxh=h, perfstepsend=MeshingStep.MESHSURFACE)
        n = len(m.FaceDescriptors()) + 1
        # 注意: SetBCName() を使うと余分な FaceDescriptor ができることがあったため
        #       名前は自前の辞書で管理する
        fd = m.Add(FaceDescriptor(surfnr=n, domin=din, domout=dout, bc=n))
        names[fd] = name
        pm = {i + 1: m.Add(MeshPoint(Pnt(*p.p))) for i, p in enumerate(s.Points())}
        for e in s.Elements2D():
            m.Add(Element2D(fd, [pm[v.nr] for v in e.vertices]))
    for i, z in zones.items():
        m.SetMaterial(i, z)
    m.GenerateVolumeMesh(maxh=maxh)
    return m, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--part", action="append", required=True, help="stl:maxh:domin:domout:patchName")
    ap.add_argument("--zone", action="append", required=True, help="domainNo:zoneName")
    ap.add_argument("--maxh", type=float, required=True)
    a = ap.parse_args()
    parts = []
    for p in a.part:
        stl, h, din, dout, name = p.split(":")
        parts.append((stl, float(h), int(din), int(dout), name))
    zones = {int(z.split(":")[0]): z.split(":")[1] for z in a.zone}
    m, names = build(parts, zones, a.maxh)
    cnt = collections.Counter(e.index for e in m.Elements3D())
    print("tets per domain:", {zones[k]: v for k, v in cnt.items()}, "points:", len(m.Points()))
    write_msh22(m, os.path.join(a.outdir, "tet.msh"), names, zones)


if __name__ == "__main__":
    main()
