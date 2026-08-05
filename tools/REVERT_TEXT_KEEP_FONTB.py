# -*- coding: utf-8 -*-
"""격리 테스트 빌드: 폰트 B는 유지, 텍스트 549개를 전부 원본으로 되돌림.
   → repack_out = 원본RDB + 폰트B만. 야구게임 진입시 크래시가:
     - 사라지면 → 원인은 '텍스트 주입'(스크립트성 CHK 손상)
     - 남으면   → 원인은 '폰트 B' 또는 다른 구조
   원본 슬롯 바이트 복사(제자리), 폰트 B 슬롯은 건드리지 않음. RDI 불변."""
import os, sys, struct, bisect
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"; OUT="repack_out"
deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t0 in tabo:
    loc0=R.locate(t0["stored"],t0["flag"])
    if loc0: laid[loc0[0]].append(loc0[1])
for k0 in laid: laid[k0].sort()
orig_fs={k0:os.path.getsize(k0) for k0 in laid}
def gap_of(rdb,off):
    arr=laid[rdb]; j=bisect.bisect_right(arr,off)
    return (arr[j] if j<len(arr) else orig_fs[rdb])-off

files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read(); kb=open(os.path.join("repack_in",fn),'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        targets.append(fn)
print(f"텍스트 원복 대상: {len(targets)}개 (폰트 B 유지)")
rf={rdb: open(rdb,"rb") for rdb in laid}
wf={rdb: open(os.path.join(OUT,rdb),"r+b") for rdb in laid}
CH=8*1024*1024
try:
    done=0; total=0
    for fn in targets:
        t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc
        n=gap_of(rdb,off)
        rf[rdb].seek(off); wf[rdb].seek(off); remain=n
        while remain>0:
            c=rf[rdb].read(min(CH,remain))
            if not c: break
            wf[rdb].write(c); remain-=len(c)
        total+=n; done+=1
        if done%150==0: print(f"  {done}/{len(targets)} ({total/1e6:.0f}MB)")
finally:
    for f in rf.values(): f.close()
    for f in wf.values(): f.close()
import shutil
shutil.copy2("RES00.RDI", os.path.join(OUT,"RES00.RDI"))
print(f"완료: {done}개 원복, {total/1e6:.0f}MB. RDI=원본. 폰트B 유지.")
