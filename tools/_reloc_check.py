# -*- coding: utf-8 -*-
"""repack_out에서 재배치된(원본 대비 OFFSET 바뀐) CHK 목록 확인."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")            # 원본
decp, tabp, idxp, rsp = R.load_rdi("repack_out/RES00.RDI")  # 패치

reloc=[]
for name in idxo:
    o=idxo[name]; p=idxp.get(name)
    if p is None: continue
    if o["stored"]!=p["stored"]:
        loc=R.locate(p["stored"],p["flag"])
        reloc.append((name, o["stored"], p["stored"], loc[0] if loc else "?"))
print(f"재배치된 CHK: {len(reloc)}개")
res00=[r for r in reloc if r[3]=="RES00.RDB"]
res10=[r for r in reloc if r[3]=="RES10.RDB"]
print(f"  RES00: {len(res00)}, RES10: {len(res10)}")
print("\n재배치 목록(상위 60):")
for name,os_,ps_,rdb in reloc[:60]:
    print(f"  {name:34s} {rdb}")
