# 変更履歴

バージョン番号は [PEP 440](https://peps.python.org/pep-0440/) 形式。`.devN` が付くものは開発中の版。

## 0.1.0.dev0（2026-11-26）

最初の開発版。GUI はまだなく、メッシュ作成手順を検証するスクリプトのみ。

- STL → Netgen 多領域テトラ → polyDualMesh → snappyHexMesh（レイヤーのみ）→ MRF の基本手順（`poc/run_pipeline.sh`）
- MRF 界面をバッフル化してからデュアル化し、`stitchMesh -perfect` で縫い戻す手順（faceZone 保持によるセル数急増を回避）
- 部品 STEP + netgen.occ による、MRF 円筒が壁と交差する形状の多領域テトラ（ルートA）
- エアギャップの軸方向押し出し方式（AMI なし、MRF 界面はギャップ中央）: `poc/run_motor_gap.sh`
  - 実形状の部品 STEP を環境変数で指定して実行可能（単位換算、スロット開口・通風ダクトを含む押し出し領域）
  - 押し出し領域内の壁は `<名前>_gap` パッチに分け、レイヤーの対象外
- 既知の問題: コア端が揃っていない場合の不正面、角の少数の不正面、ハウジング等へのレイヤーの付きにくさ（`docs/design.md` §6）
