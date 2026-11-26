"""検証用のモータ風形状を部品ごとの STEP で作る (実CADの代わり)

  housing.step    : ハウジング内の空洞 (空気が入りうる全体積)
  statorCore.step : ステータコア (中空円筒, 固体)
  rotorCore.step  : ロータコア (固体)
  shaft.step      : シャフト (固体, ハウジング端面まで貫通 -> MRF円筒の端面と交差)

寸法 [m]: ロータ直径・ギャップ・コア長を指定。ロータとステータのコア長は別々に指定でき、
どちらも軸方向中央 (z=0) に揃える (=端がずれる場合は両端で同じだけずれる)。
その他の寸法はロータ半径 Rr に比例: ステータ外径 1.75Rr, ハウジング半径 2Rr,
ハウジング長 = 長い方のコア長 + 2.5Rr, シャフト半径 0.25Rr
"""
import argparse

from netgen.occ import Cylinder, Pnt, Z

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("--rotor-d", type=float, default=0.08)
ap.add_argument("--gap", type=float, default=0.002)
ap.add_argument("--stator-len", type=float, default=0.08)
ap.add_argument("--rotor-len", type=float, default=None, help="省略時はステータと同じ")
a = ap.parse_args()
Rr = a.rotor_d / 2
Rs = Rr + a.gap
Ls = a.stator_len
Lr = a.rotor_len or Ls
Lh = max(Ls, Lr) + 2.5 * Rr
parts = {
    "housing": Cylinder(Pnt(0, 0, -Lh / 2), Z, r=2 * Rr, h=Lh),
    "statorCore": Cylinder(Pnt(0, 0, -Ls / 2), Z, r=1.75 * Rr, h=Ls) - Cylinder(Pnt(0, 0, -Ls / 2), Z, r=Rs, h=Ls),
    "rotorCore": Cylinder(Pnt(0, 0, -Lr / 2), Z, r=Rr, h=Lr),
    "shaft": Cylinder(Pnt(0, 0, -Lh / 2), Z, r=0.25 * Rr, h=Lh),
}
for n, s in parts.items():
    s.WriteStep(f"{a.outdir}/{n}.step")
print("written", list(parts))
