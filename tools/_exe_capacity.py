# -*- coding: utf-8 -*-
"""exe 잘린 문구 복구 용량 측정: (1)슬랙 제자리확장 가능수, (2)redirect 필요수·포인터유무, (3)풀 크기."""
import sys, struct, json, os
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용; sys.path.insert(0,".")
import inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))

b=open("!exefs-작업/main-원본","rb").read()
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",b,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",b,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",b,0x30)
ro_lo,ro_hi=ro_mo,ro_mo+ro_sz

# pidx: VA -> 포인터 위치들
pidx=defaultdict(int)
for seg_fo,seg_sz in [(ro_fo,ro_sz),(da_fo,da_sz)]:
    for shift in (0,4):
        base=seg_fo+shift; n=(seg_sz-shift)//8
        arr=np.frombuffer(b[base:base+n*8],dtype="<u8")
        for v in arr[(arr>=ro_lo)&(arr<ro_hi)]:
            pidx[int(v)]+=1

# zero-run 풀 (.rodata, >=8)
pool=0; i=0
while i<ro_sz:
    if b[ro_fo+i]==0:
        j=i
        while j<ro_sz and b[ro_fo+j]==0: j+=1
        if j-i>=8: pool+=(j-i)
        i=j
    else: i+=1
print(f".rodata zero-run 풀(>=8): {pool:,}바이트")

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
fit=slack=redir=trunc_only=empty=0
redir_bytes=0
for s in doc["strings"]:
    ko=s.get("ko","").strip()
    for o in s["occurrences"]:
        if o["method"]!="exe": continue
        off=o["offset"]; ln=o["len"]
        if not ko: empty+=1; continue
        kob=ENC.encode(ko)
        if len(kob)<=ln: fit+=1; continue
        # 슬랙
        T=0; k=off+ln
        while k<len(b) and b[k]==0: T+=1; k+=1
        cap=ln+T-1 if T>0 else ln
        if len(kob)<=cap: slack+=1; continue
        # redirect 가능?
        va=ro_mo+(off-ro_fo)
        if pidx.get(va,0)>0: redir+=1; redir_bytes+=len(kob)+1
        else: trunc_only+=1
print(f"\nexe occ 분류:")
print(f"  원본에 딱맞음/짧음(패딩): {fit}")
print(f"  슬랙으로 제자리확장 가능: {slack}")
print(f"  redirect 필요(포인터有): {redir}  (필요 풀 {redir_bytes:,}바이트)")
print(f"  포인터無→잘림불가피: {trunc_only}")
print(f"  미번역(빈 ko): {empty}")
print(f"\n풀 충분? {pool:,} >= {redir_bytes:,} → {'예' if pool>=redir_bytes else '아니오(부족)'}")
