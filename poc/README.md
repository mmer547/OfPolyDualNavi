# PoC: 部品 STEP → Netgen → polyDualMesh → snappy レイヤー → MRF

バージョン: [`../VERSION`](../VERSION)（`0.1.0.dev0` = **開発中**。仕様・ファイル構成は今後変わります）

設計の根拠を確かめるための検証スクリプト群。詳細は [`../docs/design.md`](../docs/design.md) を参照。

## 実形状で試す（モータ、WSL）

`run_motor_gap.sh` が本命の手順です（ギャップの軸方向押し出し、AMI なし、MRF界面はギャップ中央）。

### 1. 準備（WSL の Ubuntu で一度だけ）

```sh
# OpenFOAM (Keysight / openfoam.com 版) が入っていること。bashrc の場所を確認
ls /usr/lib/openfoam/openfoam*/etc/bashrc

sudo apt install time                     # 各工程の時間・メモリの記録に使う (無くても動く)
python3 -m venv ~/ofpdn-venv && . ~/ofpdn-venv/bin/activate
pip install netgen-mesher numpy
```

### 2. CAD の用意

- **モータ軸を Z 軸（原点を通る）に合わせる**
- 部品ごとに STEP で書き出す。ファイル名がそのままパッチ名になる（英数字のみ推奨）
  - 空洞: 空気が入りうる全体積（ハウジング内の空洞を1つのソリッドにしたもの）
  - 固体: ステータコア、ロータコア、シャフト、巻線・コイルエンドなど
- ロータとステータのコアが重なっている範囲で、ギャップ（スロット開口・通風ダクトを含む）の断面が軸方向に一様であること

### 3. 実行

```sh
. ~/ofpdn-venv/bin/activate
export BASHRC=/usr/lib/openfoam/openfoam2512/etc/bashrc     # 実際のバージョンに合わせる

CAVITY=~/motor/air.step \
SOLIDS="~/motor/statorCore.step ~/motor/rotorCore.step ~/motor/shaft.step" \
SCALE=0.001 \
ROTOR_R=0.025 STATOR_R=0.0255 \
Z0=-0.03 Z1=0.03 \
EXT_R=0.028 \
MRF_Z0=-0.036 MRF_Z1=0.036 \
RPM=3000 \
./run_motor_gap.sh ~/work/case1
```

| 変数 | 意味（長さは **m**、SCALE 適用後の値） |
|---|---|
| `CAVITY` / `SOLIDS` | 空洞 / 固体部品の STEP |
| `SCALE` | STEP 座標の倍率（STEP が mm なら `0.001`） |
| `ROTOR_R` / `STATOR_R` | ロータ外径の半径 / ステータ内径の半径 |
| `Z0` / `Z1` | ロータとステータのコアが**重なっている範囲**の下端 / 上端（ここだけ押し出す） |
| `EXT_R` | 押し出し領域の半径。`Z0..Z1` で、この半径の円筒面が全て固体（ステータヨークなど）の中にあること。スロット開口やダクトはこの内側にあれば一緒に押し出される |
| `MRF_Z0` / `MRF_Z1` | MRF円筒の下端 / 上端（半径は既定でギャップ中央、`MRF_R` で変更可） |
| `ROTOR_NAME` / `STATOR_NAME` | ロータコア / ステータコアの STEP のファイル名（拡張子なし）。既定 `rotorCore` / `statorCore` |
| `RPM` | 回転数（`constant/MRFProperties` の `omega` に換算） |
| 任意 | `DZ` 軸方向刻み、`HG` / `HE` 押し出し端面とその辺の要素サイズ、`H` 全体、`HC` コア面、`LAYERS` 層数、`FIRST` 第1層厚、`MEDIAL` nMedialAxisIter |

出力: `<workdir>/constant/polyMesh`（cellZone `MRF_rotor` 付き）、`constant/MRFProperties`、各工程のログ `log.*`。
押し出し領域内の壁は `<名前>_gap` パッチに分かれ、レイヤーは入らない。

### 既知の問題（0.1.0.dev0 時点）

- **コア端が揃っていない場合**、はみ出したコアの角のすぐ脇を MRF 界面が通る所で、デュアル化後に不正面が数十〜数百個出る（`docs/design.md` §6.6）
- ステータコア外径などの角で、少数の不正面が出ることがある（§6.4）
- ハウジングやロータ端面にレイヤーが付きにくい（§6.7）
- Keysight 最新版では未確認（v1912 で検証）。コマンドのオプションが違う場合はログ `log.<工程名>` を確認

## 検証用の形状で試す

```sh
./run_motor_gap.sh /path/to/workdir                                   # 既定: ロータ直径 80mm, ギャップ 2mm
RD=0.05 GAP=0.0005 LS=0.06 LR=0.066 ./run_motor_gap.sh /path/to/workdir   # コア端不一致
./run_pipeline.sh /path/to/workdir     # 最初の検証 (STL、MRF円筒が完全に内部)
```

## ファイル

| ファイル | 内容 |
|---|---|
| `run_motor_gap.sh` | **本命**: ギャップ押し出し方式の全工程（実形状 / 検証形状） |
| `occ_motor_gap.py` | 部品 STEP → 押し出し領域を除外し、両端面を周期境界で同一分割にした多領域テトラ |
| `make_motor_steps.py` | 検証用のモータ風形状の部品 STEP（寸法、コア長不一致、スロット開口、mm 出力を指定可） |
| `ng2msh.py` | Netgen → Gmsh 2.2（物理名付き、テトラの向き補正） |
| `foamreader.py` | polyMesh リーダ、MRF界面のずれ・界面セルの厚さの評価 |
| `case_template/` | 各工程の辞書の雛形 |
| `occ_multidomain.py` / `run_motor.sh` | ギャップを押し出さない方式（比較用） |
| `netgen_multidomain.py` / `make_test_geometry.py` / `run_pipeline.sh` | 最初の検証（STL、MRF円筒が完全に内部） |
