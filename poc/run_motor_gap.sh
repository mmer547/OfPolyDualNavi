#!/bin/bash
# ギャップ押し出し方式 (AMI なし) の検証: モータ風形状, MRF界面はギャップ中央
#   1) ギャップの円環を除いて netgen.occ でテトラ (両端の円環面は周期境界で同一分割)
#   2) 界面バッフル化 -> polyDualMesh -> 界面縫合
#   3) 下端の円環面を軸方向に押し出してギャップを埋め、両端を stitchMesh -perfect
#   4) ギャップ内の壁を別パッチに分け、それ以外の壁にだけ snappy でレイヤー
# usage: [RD=ロータ直径] [GAP=ギャップ] [LS=ステータコア長] [LR=ロータコア長] [DZ=軸方向刻み] \
#        [HG=円環maxh] [HE=円環の壁側maxh] ./run_motor_gap.sh <workdir>
#   既定: RD=0.08 GAP=0.002 LS=LR=0.08 DZ=0.002 HG=GAP/4 HE=GAP/8 (単位 m)
#   コア端が揃っていない場合 (LR != LS) は、重なっている範囲だけを押し出す
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mkdir -p "$1" && cd "$1" && pwd)
eval "$(python3 - <<PY
import math
RD=float("${RD:-0.08}"); GAP=float("${GAP:-0.002}"); LS=float("${LS:-0.08}"); LR=float("${LR:-0}") or LS
DZ=float("${DZ:-0.002}"); HG=float("${HG:-0}") or GAP/4; HE=float("${HE:-0}") or GAP/8
Rr=RD/2; Rs=Rr+GAP; Rm=Rr+GAP/2
Z1=min(LS,LR)/2; Z0=-Z1; LC=2*Z1; NZ=max(1,round(LC/DZ))
MH=LR/2+0.25*Rr          # MRF円筒の半長 (ロータ端から 0.25Rr はみ出す)
for k,v in dict(GAP=GAP,LS=LS,LR=LR,HG=HG,HE=HE,Rr=Rr,Rs=Rs,Rm=Rm,Z0=Z0,Z1=Z1,LC=LC,NZ=NZ,MH=MH,
                ML=2*MH,H=Rr/4,HC=4*GAP,RGAPF=Rs+GAP/4,LOCY=1.9*Rr,RD=RD).items():
    print(f"{k}={v:.10g}")
PY
)"
echo "RD=$RD GAP=$GAP LS=$LS LR=$LR  押し出し範囲 $Z0..$Z1 ($NZ 分割)  円環 maxh $HG / 壁側 $HE"
BASHRC=${BASHRC:-/usr/share/openfoam/etc/bashrc}
set +u; source "$BASHRC" >/dev/null 2>&1; set -u
cd "$W"; rm -rf system constant 0 ext; cp -r "$HERE/case_template/system" .
T(){ local n=$1; shift; /usr/bin/time -f "  [$n] %e s, %M KB" "$@" > log.$n 2> time.$n || { tail -20 log.$n; exit 1; }; tail -1 time.$n; }
cm(){ checkMesh > log.checkMesh.$1 2>&1; echo "  checkMesh($1): $(grep -E '^\s+cells:' log.checkMesh.$1 | xargs) $(grep -E 'Mesh OK|Failed' log.checkMesh.$1) $(grep -oE 'pyramids: [0-9]+' log.checkMesh.$1 || true)"; }
iface(){ python -W ignore "$HERE/foamreader.py" constant/polyMesh MRF_rotor 0 0 0 0 0 1 $Rm $MH || echo "  (界面の計測に失敗)"; }
patchdict(){ cat > system/createPatchDict.$1 <<EOD
FoamFile { version 2.0; format ascii; class dictionary; object createPatchDict; }
pointSync false;
patches ( $2 );
EOD
}

echo "=== netgen.occ (ギャップ除外)"
python "$HERE/make_motor_steps.py" . --rotor-d $RD --gap $GAP --stator-len $LS --rotor-len $LR >/dev/null
T netgen python "$HERE/occ_motor_gap.py" . --cavity housing.step --solid statorCore.step --solid rotorCore.step \
  --solid shaft.step --mrf "0,0,-$MH:0,0,1:$Rm:$ML" --gap "$Rr:$Rs:$Z0:$Z1" --maxh "$H" \
  --gap-h "$HG" --gap-edge-h "$HE" --local-h rotorCore:$HC --local-h statorCore:$HC --local-h mrfInterface:$HC
grep -E "^(tets|ring)" log.netgen

echo "=== テトラ -> ポリ"
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

echo "=== ギャップの押し出し ($NZ 分割) と縫合"
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

echo "=== MRF cellZone とギャップ壁パッチの分離"
cat > system/topoSetDict <<EOD
FoamFile { version 2.0; format ascii; class dictionary; object topoSetDict; }
actions
(
    { name rotorCells; type cellSet; action new; source cylinderToCell; sourceInfo { p1 (0 0 -$MH); p2 (0 0 $MH); radius $Rm; } }
    { name MRF_rotor; type cellZoneSet; action new; source setToCellZone; sourceInfo { set rotorCells; } }
    // ギャップ内の壁: コア長の範囲で、半径が Rs よりわずかに大きい円筒の内側にある面
    { name gapFaces; type faceSet; action new; source cylinderToFace; sourceInfo { p1 (0 0 $Z0); p2 (0 0 $Z1); radius $RGAPF; } }
    { name rotorGapFaces; type faceSet; action new; source patchToFace; sourceInfo { name rotorCore; } }
    { name rotorGapFaces; type faceSet; action subset; source faceToFace; sourceInfo { set gapFaces; } }
    { name statorGapFaces; type faceSet; action new; source patchToFace; sourceInfo { name statorCore; } }
    { name statorGapFaces; type faceSet; action subset; source faceToFace; sourceInfo { set gapFaces; } }
);
EOD
T topoSet topoSet
patchdict gap "{ name rotorGap; patchInfo { type wall; } constructFrom set; set rotorGapFaces; }
    { name statorGap; patchInfo { type wall; } constructFrom set; set statorGapFaces; }"
T createPatchGap createPatch -overwrite -dict system/createPatchDict.gap; rm -rf 0
T createPatch createPatch -overwrite; rm -rf 0
cm stitched
iface
cp -r constant/polyMesh polyMesh.stitched

echo "=== snappy レイヤー (ギャップ外の壁のみ)"
LOCY=$LOCY python3 - <<'PY'
import re, os
s=open("system/snappyHexMeshDict").read()
s=re.sub(r"layers\s*\{.*?\n    \}", 'layers\n    {\n        "(rotorCore|statorCore|shaft|housing)" { nSurfaceLayers 3; }\n    }', s, flags=re.S)
s=s.replace("firstLayerThickness 0.0015;","firstLayerThickness 0.0001;").replace("minThickness        0.0002;","minThickness        0.00002;")
s=s.replace("locationInMesh (0.15 0.15 0.25);",f"locationInMesh (0 {os.environ['LOCY']} 0);").replace("nLayerIter          50;","nLayerIter          20;")
open("system/snappyHexMeshDict","w").write(s)
PY
T snappy snappyHexMesh -overwrite; rm -rf 0
grep -A9 "overall thickness" log.snappy | tail -7
cm final
grep -E "^\s+MRF_rotor\s+[0-9]+\s+[0-9]+\s+[0-9.e-]+" log.checkMesh.final || true
iface
