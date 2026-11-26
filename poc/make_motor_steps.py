"""検証用のモータ風形状を部品ごとの STEP で作る (実CADの代わり)

  housing.step : ハウジング内の空洞 (空気が入りうる全体積)
  stator.step  : ステータコア (中空円筒, 固体)
  rotor.step   : ロータコア (固体)
  shaft.step   : シャフト (固体, ハウジング端面まで貫通 -> MRF円筒の端面と交差)
寸法 [m] は引数で変更可。gap = ステータ内径 - ロータ外径
"""
import argparse

from netgen.occ import Cylinder, Pnt, Z

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("--gap", type=float, default=0.002)
a = ap.parse_args()
Rr, Lc = 0.04, 0.08          # ロータ半径, コア長
Rs = Rr + a.gap              # ステータ内径
parts = {
    "housing": Cylinder(Pnt(0, 0, -0.1), Z, r=0.08, h=0.2),
    "stator": Cylinder(Pnt(0, 0, -Lc / 2), Z, r=0.07, h=Lc) - Cylinder(Pnt(0, 0, -Lc / 2), Z, r=Rs, h=Lc),
    "rotor": Cylinder(Pnt(0, 0, -Lc / 2), Z, r=Rr, h=Lc),
    "shaft": Cylinder(Pnt(0, 0, -0.1), Z, r=0.01, h=0.2),
}
for n, s in parts.items():
    s.WriteStep(f"{a.outdir}/{n}.step")
print("written", list(parts))
