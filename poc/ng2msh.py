"""Netgen Mesh -> Gmsh 2.2 ASCII 書き出し (gmshToFoam 用)

- 面要素: physical tag = FaceDescriptor番号 (1始まり) -> パッチ名 / 内部面は faceZone
- 体積要素: physical tag = 1000 + 領域番号 -> cellZone
- Netgen と Gmsh ではテトラの頂点順(向き)が逆なので入れ替える
  (入れ替えないと gmshToFoam 後に全セルが負体積になる: 検証済)
"""


def write_msh22(mesh, path, patch_names, zone_names, fd2tag=None):
    """fd2tag: FaceDescriptor番号 -> 物理タグ (同名の面をまとめる場合)"""
    fd2tag = fd2tag or {}
    P = mesh.Points()
    E2 = mesh.Elements2D()
    E3 = mesh.Elements3D()
    with open(path, "w") as f:
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n")
        f.write(f"{len(patch_names) + len(zone_names)}\n")
        for i, n in patch_names.items():
            f.write(f'2 {i} "{n}"\n')
        for i, n in zone_names.items():
            f.write(f'3 {1000 + i} "{n}"\n')
        f.write(f"$EndPhysicalNames\n$Nodes\n{len(P)}\n")
        for i, p in enumerate(P):
            x, y, z = p.p
            f.write(f"{i + 1} {x:.12g} {y:.12g} {z:.12g}\n")
        f.write(f"$EndNodes\n$Elements\n{len(E2) + len(E3)}\n")
        k = 0
        for e in E2:
            k += 1
            t = fd2tag.get(e.index, e.index)
            f.write(f"{k} 2 2 {t} {t} " + " ".join(str(v.nr) for v in e.vertices) + "\n")
        for e in E3:
            v = [x.nr for x in e.vertices]
            v[0], v[1] = v[1], v[0]
            k += 1
            f.write(f"{k} 4 2 {1000 + e.index} {1000 + e.index} " + " ".join(map(str, v)) + "\n")
        f.write("$EndElements\n")
