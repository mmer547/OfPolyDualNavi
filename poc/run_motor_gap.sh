#!/bin/bash
# OfPolyDualNavi PoC: ギャップ押し出し方式 (AMI なし) のメッシュ作成
#   1) 押し出し領域 (エアギャップ等) を除いて netgen.occ でテトラ (両端面は周期境界で同一分割)
#   2) MRF界面をバッフル化 -> polyDualMesh -> 界面を縫合
#   3) 下端面を軸方向に押し出して押し出し領域を埋め、両端を stitchMesh -perfect で縫合
#   4) MRF cellZone を作り、押し出し領域内の壁を <名前>_gap パッチに分け、それ以外の壁にレイヤー
#
# ---- 実形状で使う場合 (環境変数で指定。長さの単位は m) ----
#   CAVITY=空洞.step       空気が入りうる全体積 (ハウジング内空洞) の STEP
#   SOLIDS="a.step b.step" 固体部品の STEP (ステータコア, ロータコア, シャフト, 巻線など)。ファイル名がパッチ名
#   SCALE=0.001            STEP 座標の倍率 (STEP が mm なら 0.001)
#   ROTOR_R / STATOR_R     ロータ外径半径 / ステータ内径半径 [m]
#   Z0 / Z1                ロータとステータのコアが重なっている範囲の下端 / 上端 [m]
#   EXT_R                  押し出し領域の半径 [m]。Z0..Z1 で、この半径の円筒面が全て固体 (ステータヨーク等)
#                          の中に入ること (スロット開口や通風ダクトはこの内側にあれば一緒に押し出される)
#   MRF_Z0 / MRF_Z1        MRF円筒の下端 / 上端 [m]
#   (任意) MRF_R=ギャップ中央, ROTOR_NAME=rotorCore, STATOR_NAME=statorCore, RPM=0,
#          DZ=軸方向刻み(既定 min(3*GAP, 重なり長/30)), HG=端面maxh(既定 GAP/4), HE=端面の辺maxh(既定 GAP/8), H=全体maxh, HC=コア面maxh,
#          LAYERS=3, FIRST=第1層厚(既定 GAP/20), MEDIAL=8 (nMedialAxisIter)
#   前提: モータ軸 = Z 軸 (原点を通る)。Z0..Z1 で押し出し領域の断面が一様 (スキューなし)
#   例: CAVITY=~/motor/air.step SOLIDS="~/motor/statorCore.step ~/motor/rotorCore.step ~/motor/shaft.step" \
#       SCALE=0.001 ROTOR_R=0.025 STATOR_R=0.0255 Z0=-0.03 Z1=0.03 EXT_R=0.028 MRF_Z0=-0.036 MRF_Z1=0.036 \
#       RPM=3000 ./run_motor_gap.sh ~/work/case1
#
# ---- 検証用形状で使う場合 (CAVITY を指定しない) ----
#   RD=ロータ直径 GAP=ギャップ LS=ステータコア長 LR=ロータコア長 DZ=軸方向刻み ./run_motor_gap.sh <workdir>
#   既定: RD=0.08 GAP=0.002 LS=LR=0.08 DZ=0.002
#
# OpenFOAM: BASHRC=<openfoam の etc/bashrc> (既定 /usr/share/openfoam/etc/bashrc)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
VERSION=$(cat "$HERE/../VERSION" 2>/dev/null || echo unknown)
W=$(mkdir -p "$1" && cd "$1" && pwd)
echo "OfPolyDualNavi PoC $VERSION  (case: $W)"

if [ -z "${CAVITY:-}" ]; then
  MODE=synthetic
  eval "$(python3 - <<PY
RD=float("${RD:-0.08}"); GAP=float("${GAP:-0.002}"); LS=float("${LS:-0.08}"); LR=float("${LR:-0}") or LS
Rr=RD/2
print(f"ROTOR_R={Rr:.10g} STATOR_R={Rr+GAP:.10g} Z1={min(LS,LR)/2:.10g} Z0={-min(LS,LR)/2:.10g}")
print(f"EXT_R={(Rr+GAP+1.75*Rr)/2:.10g} MRF_Z1={LR/2+0.25*Rr:.10g} MRF_Z0={-(LR/2+0.25*Rr):.10g}")
print(f"SYN_ARGS='--rotor-d {RD} --gap {GAP} --stator-len {LS} --rotor-len {LR}'")
PY
)"
else
  MODE=real
  : "${SOLIDS:?SOLIDS を指定}" "${ROTOR_R:?}" "${STATOR_R:?}" "${Z0:?}" "${Z1:?}" "${EXT_R:?}" "${MRF_Z0:?}" "${MRF_Z1:?}"
fi
eval "$(python3 - <<PY
Rr=float("$ROTOR_R"); Rs=float("$STATOR_R"); g=Rs-Rr; z0=float("$Z0"); z1=float("$Z1")
DZ=float("${DZ:-0}") or min(g*3, (z1-z0)/30)
d=dict(GAP=g, MRF_R=float("${MRF_R:-0}") or Rr+g/2, DZ=DZ, NZ=max(1,round((z1-z0)/DZ)), LC=z1-z0,
       HG=float("${HG:-0}") or g/4, HE=float("${HE:-0}") or g/8, H=float("${H:-0}") or Rr/4,
       HC=float("${HC:-0}") or 4*g, FIRST=float("${FIRST:-0}") or g/20,
       MZC=(float("$MRF_Z0")+float("$MRF_Z1"))/2, MZH=(float("$MRF_Z1")-float("$MRF_Z0"))/2,
       ZE=DZ/4)
for k,v in d.items(): print(f"{k}={v:.10g}")
PY
)"
ROTOR_NAME=${ROTOR_NAME:-rotorCore}; STATOR_NAME=${STATOR_NAME:-statorCore}
LAYERS=${LAYERS:-3}; MEDIAL=${MEDIAL:-8}; RPM=${RPM:-0}
echo "mode=$MODE  rotorR=$ROTOR_R statorR=$STATOR_R gap=$GAP  overlap $Z0..$Z1 ($NZ x $DZ)  extR=$EXT_R  MRF R=$MRF_R z=$MRF_Z0..$MRF_Z1"

BASHRC=${BASHRC:-/usr/share/openfoam/etc/bashrc}
set +u; source "$BASHRC" >/dev/null 2>&1; set -u
cd "$W"; rm -rf system constant 0 ext; cp -r "$HERE/case_template/system" .
if [ -x /usr/bin/time ]; then TIMECMD=(/usr/bin/time -f "%e s, %M KB"); else TIMECMD=(); fi
T(){ local n=$1; shift; local t0=$SECONDS
     "${TIMECMD[@]}" "$@" > log.$n 2> time.$n || { tail -20 log.$n; tail -3 time.$n; echo "!! $n で失敗"; exit 1; }
     echo "  [$n] $(tail -1 time.$n 2>/dev/null | grep -E 's, ' || echo "$((SECONDS-t0)) s")"; }
cm(){ checkMesh > log.checkMesh.$1 2>&1; echo "  checkMesh($1): $(grep -E '^\s+cells:' log.checkMesh.$1 | xargs) $(grep -E 'Mesh OK|Failed' log.checkMesh.$1) $(grep -oE 'pyramids: [0-9]+' log.checkMesh.$1 || true)"; }
iface(){ python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 $MZC 0 0 1 $MRF_R $MZH || echo "  (界面の計測に失敗)"; }
patchdict(){ printf 'FoamFile { version 2.0; format ascii; class dictionary; object createPatchDict; }\npointSync false;\npatches ( %s );\n' "$2" > system/createPatchDict.$1; }
patches(){ python3 -c "
import re; s=open('constant/polyMesh/boundary').read()
print(' '.join(n for n,t in re.findall(r'\n\s+(\w+)\s*\{\s*type\s+(\w+);', s) if t=='wall'))"; }

echo "=== 1) netgen.occ"
if [ $MODE = synthetic ]; then
  python "$HERE/make_motor_steps.py" . $SYN_ARGS >/dev/null
  CAVARG=housing.step; SOLARGS="--solid statorCore.step --solid rotorCore.step --solid shaft.step"; SC=1
else
  CAVARG=$(eval echo "$CAVITY"); SOLARGS=""; for s in $SOLIDS; do SOLARGS="$SOLARGS --solid $(eval echo "$s")"; done; SC=${SCALE:-1}
fi
T netgen python "$HERE/occ_motor_gap.py" . --scale "$SC" --cavity "$CAVARG" $SOLARGS \
  --mrf "0,0,$MRF_Z0:0,0,1:$MRF_R:$(python3 -c "print($MRF_Z1-($MRF_Z0))")" --extrude "$EXT_R:$Z0:$Z1" \
  --rotor-r "$ROTOR_R" --stator-r "$STATOR_R" --rotor-name "$ROTOR_NAME" --stator-name "$STATOR_NAME" \
  --maxh "$H" --gap-h "$HG" --gap-edge-h "$HE" \
  --local-h "$ROTOR_NAME:$HC" --local-h "$STATOR_NAME:$HC" --local-h "mrfInterface:$HC"
grep -E "^(extrusion|tets|ring|patches|overhang)" log.netgen

echo "=== 2) テトラ -> ポリ"
T gmshToFoam gmshToFoam tet.msh
sed -i 's/type            patch;\(\s*\)$/type            wall;/' constant/polyMesh/boundary
sed -i -E '/^\s+gap(Lo|Hi)(R|S)$/{n;n;s/type            wall;/type            patch;/}' constant/polyMesh/boundary
cm tet
T createBaffles createBaffles -overwrite
T split mergeOrSplitBaffles -split -overwrite
T polyDualMesh polyDualMesh -overwrite -doNotPreserveFaceZones -concaveMultiCells 60
T stitchIface stitchMesh -perfect -overwrite mrfStator mrfRotor; rm -rf 0
rm -f constant/polyMesh/*Zones constant/polyMesh/meshModifiers
patchdict ring "{ name gapLo; patchInfo { type patch; } constructFrom patches; patches (gapLoR gapLoS); }
    { name gapHi; patchInfo { type patch; } constructFrom patches; patches (gapHiR gapHiS); }"
T createPatchRing createPatch -overwrite -dict system/createPatchDict.ring; rm -rf 0
cm dual

echo "=== 3) 押し出し ($NZ 分割) と縫合"
mkdir -p ext/system; cp system/controlDict system/fvSchemes system/fvSolution ext/system/
cat > ext/system/extrudeMeshDict <<EOD
FoamFile { version 2.0; format ascii; class dictionary; object extrudeMeshDict; }
constructFrom patch; sourceCase "$W"; sourcePatches (gapLo); exposedPatchName gapHi;
flipNormals false; extrudeModel linearDirection; nLayers $NZ; expansionRatio 1.0;
linearDirectionCoeffs { direction (0 0 1); thickness $LC; }
mergeFaces false; mergeTol 0;
EOD
(cd ext && T extrude extrudeMesh)
# 押し出しメッシュでは、元の名前 gapLo が上端(z=Z1)、exposed の gapHi が下端(z=Z0)になる
sed -i 's/^\(\s*\)gapLo$/\1extTop/; s/^\(\s*\)gapHi$/\1extBottom/' ext/constant/polyMesh/boundary
T mergeMeshes mergeMeshes -overwrite . ext; rm -rf 0
T stitchLo stitchMesh -perfect -overwrite gapLo extBottom; rm -rf 0
T stitchHi stitchMesh -perfect -overwrite gapHi extTop; rm -rf 0
rm -f constant/polyMesh/*Zones constant/polyMesh/meshModifiers

echo "=== 4) MRF cellZone と押し出し領域内の壁パッチの分離"
WALLS=$(patches)
python3 - "$WALLS" <<PY
import sys
walls=sys.argv[1].split()
acts=['{ name rotorCells; type cellSet; action new; source cylinderToCell; sourceInfo { p1 (0 0 $MRF_Z0); p2 (0 0 $MRF_Z1); radius $MRF_R; } }',
      '{ name MRF_rotor; type cellZoneSet; action new; source setToCellZone; sourceInfo { set rotorCells; } }',
      '{ name extFaces; type faceSet; action new; source cylinderToFace; sourceInfo { p1 (0 0 $(python3 -c "print($Z0+$ZE)")); p2 (0 0 $(python3 -c "print($Z1-$ZE)")); radius $EXT_R; } }']
pd=[]
for w in walls:
    acts+=[f'{{ name {w}_gapF; type faceSet; action new; source patchToFace; sourceInfo {{ name {w}; }} }}',
           f'{{ name {w}_gapF; type faceSet; action subset; source faceToFace; sourceInfo {{ set extFaces; }} }}']
    pd.append(f'{{ name {w}_gap; patchInfo {{ type wall; }} constructFrom set; set {w}_gapF; }}')
open("system/topoSetDict","w").write("FoamFile { version 2.0; format ascii; class dictionary; object topoSetDict; }\nactions\n(\n    "+"\n    ".join(acts)+"\n);\n")
open("system/createPatchDict.gap","w").write("FoamFile { version 2.0; format ascii; class dictionary; object createPatchDict; }\npointSync false;\npatches\n(\n    "+"\n    ".join(pd)+"\n);\n")
PY
T topoSet topoSet
T createPatchGap createPatch -overwrite -dict system/createPatchDict.gap; rm -rf 0
T createPatch createPatch -overwrite; rm -rf 0
cm stitched
iface
cp -r constant/polyMesh polyMesh.stitched

echo "=== 5) snappy レイヤー (押し出し領域外の壁のみ, $LAYERS 層, 第1層 $FIRST m)"
LWALLS=$(patches | tr ' ' '\n' | grep -v '_gap$' | tr '\n' ' ')
LOC=$(python3 -c "
import re; s=open('constant/polyMesh/points').read(); s=s[s.index('}',s.index('FoamFile'))+1:]; print(re.search(r'\(([^()]+)\)', s).group(1))")
LWALLS="$LWALLS" LAYERS=$LAYERS FIRST=$FIRST MEDIAL=$MEDIAL LOC="$LOC" python3 - <<'PY'
import re, os
s=open("system/snappyHexMeshDict").read()
L="\n".join(f"        {w} {{ nSurfaceLayers {os.environ['LAYERS']}; }}" for w in os.environ["LWALLS"].split())
s=re.sub(r"layers\s*\{.*?\n    \}", "layers\n    {\n"+L+"\n    }", s, flags=re.S)
s=s.replace("firstLayerThickness 0.0015;", f"firstLayerThickness {os.environ['FIRST']};")
s=s.replace("minThickness        0.0002;", f"minThickness        {float(os.environ['FIRST'])/5};")
s=s.replace("locationInMesh (0.15 0.15 0.25);", f"locationInMesh ({os.environ['LOC']});")
s=s.replace("nLayerIter          50;", "nLayerIter          20;")
s=s.replace("nMedialAxisIter     8;", f"nMedialAxisIter     {os.environ['MEDIAL']};")
open("system/snappyHexMeshDict","w").write(s)
PY
T snappy snappyHexMesh -overwrite; rm -rf 0
grep -A$((4+$(echo $LWALLS | wc -w))) "overall thickness" log.snappy | tail -n $(($(echo $LWALLS | wc -w)+1)) || true
cm final
grep "\*\*\*" log.checkMesh.final || true
grep -E "^\s+MRF_rotor\s+[0-9]+\s+[0-9]+\s+[0-9.e-]+" log.checkMesh.final || true
iface

OMEGA=$(python3 -c "import math; print($RPM*2*math.pi/60)")
cat > constant/MRFProperties <<EOD
FoamFile { version 2.0; format ascii; class dictionary; object MRFProperties; }
MRF1
{
    cellZone    MRF_rotor;
    active      yes;
    nonRotatingPatches ();   // MRF 内の静止壁があれば列挙
    origin      (0 0 0);
    axis        (0 0 1);
    omega       $OMEGA;   // [rad/s] = $RPM rpm
}
EOD
echo "=== 完了: $W/constant/polyMesh, constant/MRFProperties"
