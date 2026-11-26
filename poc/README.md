# PoC: STL → Netgen 多領域テトラ → polyDualMesh → snappy レイヤー → MRF

設計の根拠を確かめるための検証スクリプト。詳細は [`../docs/design.md`](../docs/design.md) を参照。

## 必要なもの

- OpenFOAM（openfoam.com 系列。v1912 の Ubuntu パッケージで確認済み）
- Python 3 と `pip install netgen-mesher trimesh numpy`

## 実行

```sh
./run_pipeline.sh /path/to/workdir [/path/to/openfoam/etc/bashrc]
```

検証形状（外箱・内部のMRF円筒・MRF内のハブ）を作り、全工程を実行して、各段階の `checkMesh` の結果と MRF 界面のずれを表示する。

## ファイル

| ファイル | 内容 |
|---|---|
| `make_test_geometry.py` | 検証用STLの生成 |
| `netgen_multidomain.py` | STL群から多領域テトラを生成（FaceDescriptor で領域を指定） |
| `ng2msh.py` | Netgen → Gmsh 2.2（物理名付き、テトラの向き補正） |
| `foamreader.py` | polyMesh リーダ、MRF界面のずれの評価 |
| `case_template/` | 各工程の辞書（createBaffles / topoSet / snappy レイヤーのみ / MRFProperties など） |
| `run_pipeline.sh` | 全工程の実行 |
