"""最小限の OpenFOAM polyMesh (ASCII) リーダと、MRF界面の検査 (PoC)

GUI の「品質レポート」で使う想定:
  python foamreader.py <case>/constant/polyMesh rotor  0 0 0  0 0 1  0.1 0.075
  -> cellZone 境界上の点が理想円筒 (origin, axis, R, 半長H) からどれだけずれたか
"""
import re
import sys

import numpy as np


def _body(path):
    s = open(path).read()
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"//[^\n]*", "", s)
    s = s[s.index("}", s.index("FoamFile")) + 1:]
    m = re.search(r"(\d+)\s*\(", s)
    return s[m.end():], int(m.group(1))


def read_points(d):
    b, n = _body(f"{d}/points")
    return np.array([list(map(float, x.split())) for x in re.findall(r"\(([^()]*)\)", b)[:n]])


def read_faces(d):
    # 長い面は複数行で書かれるのでトークン単位で読む
    b, n = _body(f"{d}/faces")
    tok = re.findall(r"\d+|\(|\)", b)
    F, k = [], 0
    while len(F) < n:
        m = int(tok[k])
        F.append(list(map(int, tok[k + 2:k + 2 + m])))
        k += 3 + m
    return F


def read_labels(d, name):
    b, n = _body(f"{d}/{name}")
    return np.array(b.split(")")[0].split()[:n], int)


def read_zone_cells(d, name):
    s = open(f"{d}/cellZones").read()
    s = s[s.index(f"\n{name}\n"):]
    s = s[s.index("cellLabels"):]
    m = re.search(r"(\d+)\s*\(", s)
    return np.array(s[m.end():].split(")")[0].split()[:int(m.group(1))], int)


def interface_deviation(d, zone, origin, axis, R, H):
    P = read_points(d)
    F = read_faces(d)
    own = read_labels(d, "owner")
    nei = read_labels(d, "neighbour")
    nc = max(own.max(), nei.max()) + 1
    inz = np.zeros(nc, bool)
    inz[read_zone_cells(d, zone)] = True
    ids = sorted({p for f in range(len(nei)) if inz[own[f]] != inz[nei[f]] for p in F[f]})
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    X = P[ids] - np.asarray(origin, float)
    t = X @ a
    r = np.linalg.norm(X - np.outer(t, a), axis=1)
    on_side = np.abs(r - R) <= np.abs(np.abs(t) - H)
    dev = np.where(on_side, np.abs(r - R), np.abs(np.abs(t) - H))
    return {
        "nPoints": len(ids),
        "maxDeviation": float(dev.max()),
        "maxDeviation/R": float(dev.max() / R),
        "sideRadiusRange": (float(r[on_side].min()), float(r[on_side].max())),
        "capMaxAbsAxial": float(np.abs(t[~on_side]).max()) if (~on_side).any() else None,
    }


if __name__ == "__main__":
    d, zone = sys.argv[1], sys.argv[2]
    v = list(map(float, sys.argv[3:11]))
    print(interface_deviation(d, zone, v[0:3], v[3:6], v[6], v[7]))
