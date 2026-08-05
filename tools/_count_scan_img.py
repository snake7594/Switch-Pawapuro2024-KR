# -*- coding: utf-8 -*-
"""이미지(NX SUR) 포함 + 스캔 패치(크기불변, 변경있음) CHK 식별 → 위험(이미지 손상) 목록."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
RES="RES_추출원본"
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
scan_img=[]; scan_noimg=0; string_chk=0
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o): continue
    so=os.path.getsize(o); sk=os.path.getsize(k)
    if so!=sk: string_chk+=1; continue   # STRING(크기변동)
    ob=open(o,'rb').read(); kb=open(k,'rb').read()
    if ob==kb: continue                   # 변경 없음
    has_img = ob.find(b'NX  SUR ')>=0
    if has_img:
        # 변경 바이트 수 + 변경위치가 이미지영역인지 대략
        ndiff=sum(1 for i in range(len(ob)) if ob[i]!=kb[i])
        scan_img.append((fn, so, ndiff))
    else:
        scan_noimg+=1
print(f"STRING(크기변동): {string_chk}")
print(f"스캔+이미지없음(안전): {scan_noimg}")
print(f"★ 스캔+이미지있음(위험): {len(scan_img)}")
print("\n=== 이미지 포함 스캔 CHK (변경바이트 많은 순 상위 40) ===")
for fn,sz,nd in sorted(scan_img,key=lambda x:-x[2])[:40]:
    print(f"  {fn:34s} size={sz:>9} 변경={nd}")
