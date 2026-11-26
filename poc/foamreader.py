"""最小限の OpenFOAM polyMesh (ASCII) リーダと、MRF界面の検査 (PoC)

GUI の「品質レポート」で使う想定:
  python foamreader.py <case>/constant/polyMesh MRF_rotor  0 0 0  0 0 1  0.1 0.075
  -> cellZone 境界上の点が理想円筒 (origin, axis, R, 半長H) からどれだけずれたか
     と、界面に接するセルの薄さ

数百万セルでもメモリを抑えるため、面は「平坦な頂点配列 + オフセット」の numpy 配列で持つ。
"""
import re
import sys

import numpy as np


def _body(path):
    s = open(path).read()
    i = s.index("}", s.index("FoamFile")) + 1
    s = s[i:]
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"//[^\n]*", "", s)
    m = re.search(r"(\d+)\s*\(", s)
    return s[m.end():], int(m.group(1))


def _numbers(text, dtype):
    return np.fromstring(text.replace("(", " ").replace(")", " "), dtype=dtype, sep=" ")


def read_points(d):
    b, n = _body(f"{d}/points")
    return _numbers(b, np.float64)[: 3 * n].reshape(n, 3)


def read_faces(d):
    """(offsets, verts): 面 i の頂点は verts[offsets[i]:offsets[i+1]]"""
    b, n = _body(f"{d}/faces")
    a = _numbers(b, np.int64)  # [n0, v.., n1, v.., ...]
    offs = np.empty(n + 1, np.int64)
    starts = np.empty(n, np.int64)
    k = 0
    for i in range(n):  # 長い面は複数行で書かれるが、数値列にすれば形式は同じ
        starts[i] = k + 1
        k += 1 + a[k]
    sizes = a[starts - 1]
    offs[0] = 0
    np.cumsum(sizes, out=offs[1:])
    idx = np.repeat(starts - offs[:-1], sizes) + np.arange(offs[-1])
    return offs, a[idx]


def read_labels(d, name):
    b, n = _body(f"{d}/{name}")
    return _numbers(b.split(")")[0], np.int64)[:n]


def read_zone_cells(d, name):
    s = open(f"{d}/cellZones").read()
    s = s[s.index(f"\n{name}\n"):]
    s = s[s.index("cellLabels"):]
    m = re.search(r"(\d+)\s*\(", s)
    return _numbers(s[m.end():].split(")")[0], np.int64)[: int(m.group(1))]


def face_centres(P, offs, verts):
    sizes = np.diff(offs)
    owner_face = np.repeat(np.arange(len(sizes)), sizes)
    c = np.zeros((len(sizes), 3))
    np.add.at(c, owner_face, P[verts])
    return c / sizes[:, None]


def interface_deviation(d, zone, origin, axis, R, H):
    P = read_points(d)
    offs, verts = read_faces(d)
    own = read_labels(d, "owner")
    nei = read_labels(d, "neighbour")
    nc = int(max(own.max(), nei.max())) + 1
    inz = np.zeros(nc, bool)
    inz[read_zone_cells(d, zone)] = True
    nint = len(nei)
    iface = np.nonzero(inz[own[:nint]] != inz[nei])[0]
    pos = np.concatenate([np.arange(offs[f], offs[f + 1]) for f in iface])
    ids = np.unique(verts[pos])
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    X = P[ids] - np.asarray(origin, float)
    t = X @ a
    r = np.linalg.norm(X - np.outer(t, a), axis=1)
    on_side = np.abs(r - R) <= np.abs(np.abs(t) - H)
    dev = np.where(on_side, np.abs(r - R), np.abs(np.abs(t) - H))
    # 円筒側面の界面に接するセルの「半径方向の厚さ」(面中心の半径の広がり) の最小値
    fc = face_centres(P, offs, verts) - np.asarray(origin, float)
    ft = fc @ a
    fr = np.linalg.norm(fc - np.outer(ft, a), axis=1)
    lo = np.full(nc, np.inf)
    hi = np.full(nc, -np.inf)
    for cells, n in ((own, len(own)), (nei, nint)):
        np.minimum.at(lo, cells, fr[:n])
        np.maximum.at(hi, cells, fr[:n])
    side_if = iface[np.abs(ft[iface]) < 0.98 * H]
    cells = np.unique(np.concatenate([own[side_if], nei[side_if]]))
    thick = (hi - lo)[cells]
    return {
        "nPoints": int(len(ids)),
        "maxDeviation": float(dev.max()),
        "maxDeviation/R": float(dev.max() / R),
        "sideRadiusRange": (float(r[on_side].min()), float(r[on_side].max())),
        "capMaxAbsAxial": float(np.abs(t[~on_side]).max()) if (~on_side).any() else None,
        "minRadialThicknessOfInterfaceCells": float(thick.min()) if len(thick) else None,
    }


if __name__ == "__main__":
    d, zone = sys.argv[1], sys.argv[2]
    v = list(map(float, sys.argv[3:11]))
    print(interface_deviation(d, zone, v[0:3], v[3:6], v[6], v[7]))
