#!/bin/bash
# モータ風形状 (シャフトがMRF円筒を貫く) での検証: 部品STEP -> netgen.occ -> polyDualMesh -> レイヤー
# usage: ./run_motor.sh <workdir> <MRF半径> [gap] [ギャップ部のmaxh] [全体maxh]
#   ロータ半径 0.04 m。MRF半径 = 0.04+gap/2 (ギャップ中央) か 0.04+gap (ステータ内径) を想定
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mkdir -p "$1" && cd "$1" && pwd); RM=$2; GAP=${3:-0.002}; HG=${4:-0.0008}; H=${5:-0.008}
BASHRC=${BASHRC:-/usr/share/openfoam/etc/bashrc}
set +u; source "$BASHRC" >/dev/null 2>&1; set -u
cd "$W"; cp -r "$HERE/case_template/system" .
T(){ local n=$1; shift; /usr/bin/time -f "  [$n] %e s, %M KB" "$@" > log.$n 2> time.$n || { tail -20 log.$n; exit 1; }; tail -1 time.$n; }
cm(){ checkMesh > log.checkMesh.$1 2>&1; echo "  checkMesh($1): $(grep -E '^\s+cells:' log.checkMesh.$1 | xargs) $(grep -E 'Mesh OK|Failed' log.checkMesh.$1)"; }

echo "=== STEP 作成 + netgen.occ (MRF R=$RM)"
python "$HERE/make_motor_steps.py" . --gap "$GAP" >/dev/null
T netgen python "$HERE/occ_multidomain.py" . --cavity housing.step --solid statorCore.step --solid rotorCore.step \
  --solid shaft.step --mrf "0,0,-0.045:0,0,1:$RM:0.09" --maxh "$H" \
  --local-h rotorCore:$HG --local-h statorCore:$HG --local-h mrfInterface:$HG
grep -E "^tets" log.netgen
echo "=== OpenFOAM"
T gmshToFoam gmshToFoam tet.msh
sed -i 's/type            patch;\(\s*\)$/type            wall;/' constant/polyMesh/boundary
cm tet
T createBaffles createBaffles -overwrite
T split mergeOrSplitBaffles -split -overwrite
T polyDualMesh polyDualMesh -overwrite -doNotPreserveFaceZones -concaveMultiCells 60
T stitchMesh stitchMesh -perfect -overwrite mrfStator mrfRotor; rm -rf 0
rm -f constant/polyMesh/*Zones
sed -i "s/p1 (0 0 -0.075); p2 (0 0 0.075); radius 0.1;/p1 (0 0 -0.045); p2 (0 0 0.045); radius $RM;/" system/topoSetDict
T topoSet topoSet; T createPatch createPatch -overwrite; rm -rf 0
cm dual
python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 0 0 0 1 "$RM" 0.045 || echo "  (界面の計測に失敗)"
cp -r constant/polyMesh polyMesh.dual
python - <<'PY'
import re
s=open("system/snappyHexMeshDict").read()
s=re.sub(r"layers\s*\{.*?\n    \}", 'layers\n    {\n        "(rotorCore|statorCore|shaft|housing)" { nSurfaceLayers 3; }\n    }', s, flags=re.S)
s=s.replace("firstLayerThickness 0.0015;","firstLayerThickness 0.0001;").replace("minThickness        0.0002;","minThickness        0.00002;")
s=s.replace("locationInMesh (0.15 0.15 0.25);","locationInMesh (0 0.075 0.09);")
open("system/snappyHexMeshDict","w").write(s)
PY
T snappy snappyHexMesh -overwrite; rm -rf 0
grep -A7 "overall thickness" log.snappy | tail -4
cm final
grep -E "\*\*\*" log.checkMesh.final || true
grep -E "^\s+MRF_rotor\s+[0-9]+\s+[0-9]+\s+[0-9.e-]+" log.checkMesh.final
python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 0 0 0 1 "$RM" 0.045 || echo "  (界面の計測に失敗)"
