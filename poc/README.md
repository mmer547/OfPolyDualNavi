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
| `run_pipeline.sh` | 全工程の実行（MRF円筒が完全に内部のケース、STL入力） |
| `make_motor_steps.py` | モータ風形状の部品 STEP を生成（シャフトが MRF 円筒を貫く） |
| `occ_multidomain.py` | ルートA: 部品 STEP + MRF 円筒 → netgen.occ で界面一致の多領域テトラ |
| `run_motor.sh` | モータ風形状での全工程（`./run_motor.sh <workdir> <MRF半径> [gap] [ギャップmaxh] [全体maxh]`） |
| `occ_motor_gap.py` | ギャップ押し出し方式用: ギャップを除外し、両端の円環面を周期境界で同一分割にしたテトラ |
| `run_motor_gap.sh` | ギャップ押し出し方式の全工程（AMI なし。`./run_motor_gap.sh <workdir> [円環maxh] [壁側maxh] [軸方向分割数] [全体maxh]`） |

`run_motor.sh` / `run_motor_gap.sh` は GNU time（`/usr/bin/time`）で各工程の時間と最大メモリも記録する。
