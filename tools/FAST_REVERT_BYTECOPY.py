# -*- coding: utf-8 -*-
"""이미지(NX SUR) 포함 스캔 CHK를 repack_out에서 원본으로 빠르게 되돌림.
   재압축 없이 '원본 RDB의 슬롯 바이트'를 그대로 복사(제자리, 오프셋 동일).
   + RDI decsize 원복. 이미지 손상 수정."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"; OUT="repack_out"

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
decp, tabp, idxp, rsp = R.load_rdi(os.path.join(OUT,"RES00.RDI"))

# 원본 레이아웃: RDB별 정렬 오프셋(gap 계산)
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tabo:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
orig_fs={k:os.path.getsize(k) for k in laid}
import bisect
def next_off(rdb, off):
    arr=laid[rdb]; j=bisect.bisect_right(arr, off)
    return arr[j] if j<len(arr) else orig_fs[rdb]

# 대상: 이미지+스캔+변경 (크기불변, 원본과 다름, NX SUR 보유)
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o): continue
    if os.path.getsize(o)!=os.path.getsize(k): continue
    ob=open(o,'rb').read()
    if ob==open(k,'rb').read(): continue
    if ob.find(b'NX  SUR ')<0: continue
    if fn in idxo and fn in idxp: targets.append(fn)
print(f"되돌릴 대상: {len(targets)}개")

# 원본 RDB 열기(읽기), repack_out RDB 열기(쓰기)
rf={rdb: open(rdb,"rb") for rdb in ("RES00.RDB","RES10.RDB")}
wf={rdb: open(os.path.join(OUT,rdb),"r+b") for rdb in ("RES00.RDB","RES10.RDB")}
CH=8*1024*1024
try:
    done=0; total_bytes=0
    for fn in targets:
        to=idxo[fn]; loc=R.locate(to["stored"],to["flag"])
        if loc is None: continue
        rdb, off, is10 = loc
        nx=next_off(rdb, off)
        n=nx-off
        # 원본 슬롯 [off:nx] → repack_out 동일 위치 복사
        rf[rdb].seek(off); wf[rdb].seek(off)
        remain=n
        while remain>0:
            chunk=rf[rdb].read(min(CH,remain))
            if not chunk: break
            wf[rdb].write(chunk); remain-=len(chunk)
        total_bytes+=n
        # RDI decsize 원복(오프셋은 이미 원본과 동일=in-place)
        rp=rsp + idxp[fn]["i"]*9
        struct.pack_into("<I",decp,rp,to["stored"])
        struct.pack_into("<I",decp,rp+4,to["DEC_SIZE"])
        done+=1
        if done%200==0: print(f"  {done}/{len(targets)} ({total_bytes/1e6:.0f}MB)")
finally:
    for f in rf.values(): f.close()
    for f in wf.values(): f.close()
R.save_rdi(decp, os.path.join(OUT,"RES00.RDI"))
print(f"완료: {done}개 되돌림, {total_bytes/1e6:.0f}MB 복사. RDI 저장.")
print("repack_out = 폰트A + 텍스트(이미지CHK는 일본어). 스톡main과 테스트.")
