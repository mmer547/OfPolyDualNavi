#!/bin/bash
# 検証パイプライン (PoC): STL -> Netgen多領域テトラ -> polyDualMesh -> snappyレイヤー -> MRF
# usage: ./run_pipeline.sh <workdir> [openfoam bashrc]
#   python 環境に netgen-mesher, trimesh, numpy が必要
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mkdir -p "$1" && cd "$1" && pwd)
BASHRC=${2:-/usr/share/openfoam/etc/bashrc}
# OpenFOAM の bashrc は未定義変数を参照するので一時的に -u を外す
set +u; source "$BASHRC"; set -u

cd "$W"
cp -r "$HERE/case_template/system" "$HERE/case_template/constant" .
step(){ echo "=== $1"; }
clean0(){ rm -rf 0; }   # 前工程が 0/ に書いたファイルは次工程を壊すことがある (snappy で確認)

step "形状作成 + Netgen 多領域テトラ"
python "$HERE/make_test_geometry.py" .
python "$HERE/netgen_multidomain.py" . --maxh 0.03 \
    --part walls.stl:0.03:1:0:walls --part mrf.stl:0.012:2:1:mrfInterface --part hub.stl:0.008:0:2:hub \
    --zone 1:stator --zone 2:MRF_rotor 2>&1 | grep -E "^tets"

step "gmshToFoam (物理ボリューム->cellZone, 内部の物理サーフェス->faceZone)"
gmshToFoam tet.msh > log.gmshToFoam 2>&1
sed -i 's/type            patch;\(\s*\)$/type            wall;/' constant/polyMesh/boundary   # PoC: 全パッチを wall に
checkMesh > log.checkMesh.tet 2>&1; grep -E "^\s+(points|cells):|Mesh OK|Failed" log.checkMesh.tet

step "界面をバッフル化して点を分割"
createBaffles -overwrite > log.createBaffles 2>&1
mergeOrSplitBaffles -split -overwrite > log.mergeOrSplitBaffles 2>&1

step "polyDualMesh"
# createBaffles が faceZone を作るので -doNotPreserveFaceZones が必須
# (保持すると界面の全点が特徴点扱いになり、界面沿いに微小六面体の帯ができてセル数が約4倍になる)
polyDualMesh -overwrite -doNotPreserveFaceZones -concaveMultiCells 60 > log.polyDualMesh 2>&1

step "縫合 + cellZone 再作成 + 空パッチ削除"
stitchMesh -perfect -overwrite mrfStator mrfRotor > log.stitchMesh 2>&1; clean0
rm -f constant/polyMesh/cellZones constant/polyMesh/faceZones constant/polyMesh/pointZones
topoSet > log.topoSet 2>&1
createPatch -overwrite > log.createPatch 2>&1; clean0
checkMesh > log.checkMesh.dual 2>&1; grep -E "^\s+cells:|Mesh OK|Failed" log.checkMesh.dual
python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 0 0 0 1 0.1 0.075 || echo "  (界面の計測に失敗)"

step "snappyHexMesh (addLayers のみ)"
snappyHexMesh -overwrite > log.snappyHexMesh 2>&1; clean0
grep -A6 "patch faces    layers   overall thickness" log.snappyHexMesh | tail -3
checkMesh > log.checkMesh.final 2>&1; grep -E "^\s+cells:|Mesh OK|Failed" log.checkMesh.final
grep -E "^\s+MRF_rotor\s+[0-9]" log.checkMesh.final
python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 0 0 0 1 0.1 0.075 || echo "  (界面の計測に失敗)"

step "MRF simpleFoam (動作確認のみ)"
cp -r "$HERE/case_template/0" .
simpleFoam > log.simpleFoam 2>&1 && echo "simpleFoam finished: $(grep -c '^Time =' log.simpleFoam) iterations"
