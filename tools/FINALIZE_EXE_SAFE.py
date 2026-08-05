# -*- coding: utf-8 -*-
"""exe 안전 재빌드 — redirect 완전 제거. 제자리+뒤 NUL슬랙+UTF-8 clean잘림만.
   (검증된 main-safe 방식: .text·.data·헤더 불변, 포인터 재작성 0 → 코드점프 크래시 원천봉쇄.)
   긴 문구는 슬랙까지만 복구, 초과분은 clean 잘림(겹침·bleed 없음).
   출력: inject_out/main-safe2"""
import os, sys, struct, json
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용; sys.path.insert(0,".")
import inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))
SRC="!exefs-작업/main-원본"; OUT="inject_out/main-safe2"

data=bytearray(open(SRC,"rb").read()); orig=bytes(data)
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",data,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",data,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",data,0x30)

def clean_trunc(kob, cap):
    if len(kob)<=cap: return kob
    return kob[:cap].decode("utf-8","ignore").encode("utf-8")

def write_inplace(off, ln, nb):
    T=0; k=off+ln
    while k<len(data) and data[k]==0: T+=1; k+=1
    cap=ln+T-1 if T>0 else ln
    region_end=off+ln+T
    nb2=clean_trunc(nb, cap)
    data[off:off+len(nb2)]=nb2
    data[off+len(nb2):region_end]=b"\x00"*(region_end-off-len(nb2))
    return len(nb2)==len(nb)

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
st=defaultdict(int)
for s in doc["strings"]:
    ko=s.get("ko","").strip()
    kob=ENC.encode(ko) if ko else None
    for o in s["occurrences"]:
        if o["method"]!="exe": continue
        if not ko: st["empty"]+=1; continue
        off=o["offset"]; ln=o["len"]
        if off<ro_fo or off+ln>ro_fo+ro_sz: st["skip"]+=1; continue
        if write_inplace(off, ln, kob): st["fit"]+=1
        else: st["trunc"]+=1

an=np.frombuffer(bytes(data),dtype=np.uint8); ao=np.frombuffer(orig,dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
in_tx=int(((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum())
in_da=int(((diff>=da_fo)&(diff<da_fo+da_sz)).sum())
in_hdr=int((diff<0x100).sum())
in_ro=int(((diff>=ro_fo)&(diff<ro_fo+ro_sz)).sum())
print(f"변경 {len(diff):,}B: .text={in_tx} .data={in_da} 헤더={in_hdr} .rodata={in_ro}")
assert in_tx==0 and in_da==0 and in_hdr==0 and len(data)==len(orig), "안전 위반!"
os.makedirs("inject_out", exist_ok=True); open(OUT,"wb").write(data)
print(f"제자리/슬랙 {st['fit']}, 잘림 {st['trunc']}, 미번역 {st['empty']}")
print(f"✅ {OUT} — redirect 0, .text/.data/헤더 불변, .rodata만 변경(포인터 재작성 없음)")
