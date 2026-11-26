"""ギャップ押し出し方式のためのテトラ生成 (ルートA + 押し出し領域の除外)

部品STEPから流体を作り、「押し出し領域」= 半径 Rext 以内・z0..z1 の円柱と流体の共通部分
(エアギャップ、スロット開口、ロータの通風ダクトなど) を Netgen の領域から除外する。
押し出し領域の両端面は「周期境界」で上下同一の三角形分割にし、MRF界面の円で内側(R)/外側(S)
に分かれる。デュアル化後、下端面を軸方向に押し出して埋め、上下とも stitchMesh -perfect で
縫い合わせる (AMI 不要)。

前提:
  - モータの軸は Z 軸 (原点を通る)。CAD 側で合わせておく
  - z0..z1 の範囲で、押し出し領域の断面が軸方向に一様 (スキューなし)
  - 半径 Rext の円筒面が、z0..z1 の範囲で全て固体 (ステータコアのヨークなど) の中にある
    (= 押し出し領域の側面が全て壁になる)

端面のパッチ名: gapLoR, gapLoS (下端), gapHiR, gapHiS (上端)

例 (STEP が mm 単位の場合 --scale 0.001。以降の寸法は全て m):
  python occ_motor_gap.py out --scale 0.001 --cavity housing.step --solid statorCore.step \
     --solid rotorCore.step --solid shaft.step --mrf 0,0,-0.045:0,0,1:0.041:0.09 \
     --extrude 0.05:-0.04:0.04 --rotor-r 0.040 --stator-r 0.042 \
     --maxh 0.008 --gap-h 0.0005 --gap-edge-h 0.00025 --local-h rotorCore:0.002
"""
import argparse
import collections
import os
import time

from netgen.occ import Cylinder, Glue, IdentificationType, OCCGeometry, Pnt, Z, gp_Trsf, gp_Vec

from ng2msh import write_msh22

TOL = 1e-6


def load(path, name, scale):
    s = OCCGeometry(path).shape
    if scale != 1.0:
        s = s.Scale(Pnt(0, 0, 0), scale)
    s.faces.name = name
    return s


def rmax_of(bb):
    return max(abs(bb[0][0]), abs(bb[1][0]), abs(bb[0][1]), abs(bb[1][1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--cavity", required=True, help="空気が入りうる全体積 (ハウジング内空洞) の STEP")
    ap.add_argument("--solid", action="append", default=[], help="固体部品の STEP (ファイル名がパッチ名になる)")
    ap.add_argument("--scale", type=float, default=1.0, help="STEP 座標に掛ける倍率 (mm->m なら 0.001)")
    ap.add_argument("--mrf", required=True, help="ox,oy,oz:ax,ay,az:R:L (円筒の端面中心, 軸, 半径, 長さ)")
    ap.add_argument("--extrude", required=True, help="Rext:z0:z1 押し出し領域 (半径, 下端, 上端)")
    ap.add_argument("--rotor-r", type=float, default=None, help="ロータ外径半径 (はみ出し部の細分化に使用)")
    ap.add_argument("--stator-r", type=float, default=None, help="ステータ内径半径 (同上)")
    ap.add_argument("--rotor-name", default="rotorCore")
    ap.add_argument("--stator-name", default="statorCore")
    ap.add_argument("--maxh", type=float, required=True)
    ap.add_argument("--gap-h", type=float, required=True, help="押し出し端面の maxh")
    ap.add_argument("--gap-edge-h", type=float, default=None, help="押し出し端面の辺の maxh (壁近傍の解像)")
    ap.add_argument("--grading", type=float, default=0.3)
    ap.add_argument("--local-h", action="append", default=[], help="patch:maxh")
    ap.add_argument("--edge-h", action="append", default=[], help="patch:maxh  そのパッチの面の辺の maxh")
    ap.add_argument("--overhang-h", type=float, default=0.5, help="はみ出し部の面と角の辺の maxh (ギャップ幅に対する倍率)")
    ap.add_argument("--optsteps3d", type=int, default=None, help="Netgen の体積メッシュ最適化回数")
    a = ap.parse_args()

    stem = lambda p: os.path.splitext(os.path.basename(p))[0]
    fluid = load(a.cavity, stem(a.cavity), a.scale)
    for p in a.solid:
        fluid = fluid - load(p, stem(p), a.scale)
    Rext, z0, z1 = map(float, a.extrude.split(":"))
    ext = Cylinder(Pnt(0, 0, z0), Z, r=Rext, h=z1 - z0)
    ext.faces.name = "gapRing"          # 切断でできる端面だけがこの名前を引き継ぐ
    fluid = fluid - ext

    o, ax, R, L = a.mrf.split(":")
    o = list(map(float, o.split(","))); ax = list(map(float, ax.split(",")))
    Rm = float(R)
    cyl = Cylinder(Pnt(*o), gp_Vec(*ax), r=Rm, h=float(L))
    cyl.faces.name = "mrfInterface"
    rot = fluid * cyl
    sta = fluid - cyl
    rot.mat("MRF_rotor"); sta.mat("stator")
    shape = Glue([sta, rot])

    # 押し出し端面を分類・命名し、上下を周期境界で対応づける
    ring = collections.defaultdict(list)
    for f in shape.faces:
        if f.name != "gapRing":
            continue
        bb = f.bounding_box
        if abs(bb[1][2] - bb[0][2]) > TOL:
            raise SystemExit(f"押し出し領域の側面が流体に露出しています (Rext を固体の中に): {bb}")
        side = "Lo" if abs(bb[0][2] - z0) < TOL else "Hi"
        half = "R" if rmax_of(bb) <= Rm + max(1e-5, 1e-4 * Rm) else "S"   # OCC の bbox は許容誤差分だけ大きい
        f.name = f"gap{side}{half}"
        f.maxh = a.gap_h
        if a.gap_edge_h:
            for e in f.edges:
                e.maxh = a.gap_edge_h
        ring[side + half].append(f)
    if not ring["LoR"] or not ring["LoS"] or len(ring["LoR"]) != len(ring["HiR"]) or len(ring["LoS"]) != len(ring["HiS"]):
        raise SystemExit(f"押し出し端面の検出に失敗: { {k: len(v) for k, v in ring.items()} }")
    trafo = gp_Trsf.Translation(gp_Vec(0, 0, z1 - z0))
    key = lambda f: tuple(round(v, 7) for v in (f.bounding_box[0][0], f.bounding_box[0][1], f.bounding_box[1][0], f.bounding_box[1][1]))
    npair = 0
    for half in "RS":
        his = {key(f): f for f in ring["Hi" + half]}
        for lo in ring["Lo" + half]:
            hi = his.get(key(lo))
            if hi is None:
                raise SystemExit("上下の押し出し端面の形が一致しません (断面が軸方向に一様でない?)")
            lo.Identify(hi, f"gap{half}{npair}", IdentificationType.PERIODIC, trafo)
            npair += 1
    print(f"extrusion end faces: { {k: len(v) for k, v in ring.items()} }")

    lh = dict(x.split(":") for x in a.local_h)
    for f in shape.faces:
        if f.name in lh:
            f.maxh = float(lh[f.name])
    # コア端が揃っていない場合、押し出し範囲の外に残るロータ外径面/ステータ内径面と
    # MRF界面の間は半ギャップ厚の薄い円環になる。そこを細かくする
    if a.rotor_r and a.stator_r:
        g = a.stator_r - a.rotor_r
        for f in shape.faces:
            if f.name not in (a.rotor_name, a.stator_name):
                continue
            bb = f.bounding_box
            if abs(bb[1][2] - bb[0][2]) < TOL:
                continue
            r = rmax_of(bb)
            if abs(r - a.rotor_r) < 1e-5 or abs(r - a.stator_r) < 1e-5:
                f.maxh = a.overhang_h * g
                for e in f.edges:
                    e.maxh = a.overhang_h * g
                print(f"overhang face refined: {f.name} r={r:.5f} z={bb[0][2]:.4f}..{bb[1][2]:.4f}")
    eh = dict(x.split(":") for x in a.edge_h)
    for f in shape.faces:
        if f.name in eh:
            for e in f.edges:
                e.maxh = float(eh[f.name])
    kw = {"optsteps3d": a.optsteps3d} if a.optsteps3d else {}
    t = time.time()
    m = OCCGeometry(shape).GenerateMesh(maxh=a.maxh, grading=a.grading, **kw)
    print(f"netgen: {time.time()-t:.1f}s")

    tags, fd2tag = {}, {}
    for i, fd in enumerate(m.FaceDescriptors()):
        name = "mrfInterface" if (fd.domin > 0 and fd.domout > 0) else fd.bcname
        fd2tag[i + 1] = tags.setdefault(name, len(tags) + 1)
    zones = {i + 1: m.GetMaterial(i + 1) for i in range(m.GetNDomains())}
    cnt = collections.Counter(e.index for e in m.Elements3D())
    fds = m.FaceDescriptors()
    nring = collections.Counter(fds[e.index - 1].bcname for e in m.Elements2D() if fds[e.index - 1].bcname.startswith("gap"))
    print("tets per domain:", {zones[k]: v for k, v in cnt.items()}, "points:", len(m.Points()))
    print("ring triangles:", dict(nring))
    print("patches:", sorted(tags))
    write_msh22(m, os.path.join(a.outdir, "tet.msh"), {v: k for k, v in tags.items()}, zones, fd2tag)


if __name__ == "__main__":
    main()
