# -*- coding: utf-8 -*-
"""exe(main) 완성 주입 — 잘린 긴 문구 전체복구 + 안전.
   각 문자열:
     1) 제자리(원본+뒤 NUL슬랙)에 clean 기록(짧으면 패딩, 길면 UTF-8경계 clean잘림).
        → 코드참조(ADRP+ADD) 경로는 여기서 (완전 or 잘린) 한글을 봄.
     2) 길어서 잘렸고 '8바이트정렬 데이터포인터'가 있으면 → redirect:
        전체 한글을 .rodata zero-run 풀에 쓰고, 그 VA를 가리키던 포인터들을 새 VA로 교체.
        → 데이터포인터 경로는 완전 한글을 봄.
   안전장치: 8B정렬 포인터만(진짜 64비트 포인터), 참조 32개 초과는 제외(과다=오탐 의심),
             풀은 .rodata 기존 zero-run만 사용(크기·.text·헤더 불변; .data는 포인터값만 변경).
   출력: inject_out/main-final"""
import os, sys, struct, json
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용; sys.path.insert(0,".")
import inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))
SRC="!exefs-작업/main-원본"; OUT="inject_out/main-final"

data=bytearray(open(SRC,"rb").read()); orig=bytes(data)
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",data,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",data,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",data,0x30)
ro_lo,ro_hi=ro_mo,ro_mo+ro_sz

# pidx: VA -> [file오프셋 위치들] (8B정렬 워드 값이 .rodata VA)
pidx=defaultdict(list)
for seg_fo,seg_sz in [(ro_fo,ro_sz),(da_fo,da_sz)]:
    n=seg_sz//8
    arr=np.frombuffer(bytes(data[seg_fo:seg_fo+n*8]),dtype="<u8")
    for i in np.nonzero((arr>=ro_lo)&(arr<ro_hi))[0]:
        pidx[int(arr[i])].append(seg_fo+int(i)*8)

# zero-run 풀 (.rodata, >=8). 앞 8바이트는 '가리켜지는 빈문자열'일 수 있어 스킵.
runs=[]; i=0
while i<ro_sz:
    if data[ro_fo+i]==0:
        j=i
        while j<ro_sz and data[ro_fo+j]==0: j+=1
        if j-i>=16: runs.append([i+8, j-i-8])   # 앞 8B 여유 스킵
        i=j
    else: i+=1
runs.sort(key=lambda r:-r[1])
def alloc(need):
    for r in runs:
        if r[1]>=need:
            pos=r[0]; r[0]+=need; r[1]-=need; return pos
    return None

def clean_trunc(kob, cap):
    if len(kob)<=cap: return kob
    return kob[:cap].decode("utf-8","ignore").encode("utf-8")

def write_inplace(off, ln, nb):
    """제자리+슬랙에 clean 기록. 반환: 완전히 들어갔나(True=슬랙내 fit)."""
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
        if off<ro_fo or off+ln>ro_fo+ro_sz: st["skip_range"]+=1; continue
        va=ro_mo+(off-ro_fo)
        full=write_inplace(off, ln, kob)           # 1) 제자리(코드참조 경로)
        if full: st["inplace"]+=1; continue
        # 2) 길어서 잘림 → redirect 시도
        locs=pidx.get(va, [])
        if 0<len(locs)<=32:
            need=len(kob)+1
            pos=alloc(need)
            if pos is not None:
                nfo=ro_fo+pos; nva=ro_mo+pos
                data[nfo:nfo+len(kob)]=kob; data[nfo+len(kob)]=0
                for loc in locs: struct.pack_into("<Q",data,loc,nva)
                st["redirect"]+=1; continue
            else: st["pool_full"]+=1
        st["trunc"]+=1

# 안전 검증: .text·헤더 불변, .data 변경은 8B포인터 값교체만
an=np.frombuffer(bytes(data),dtype=np.uint8); ao=np.frombuffer(orig,dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
in_tx=((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum()
in_hdr=(diff<0x100).sum()
print(f"변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr} (0이어야 함)")
assert in_tx==0 and in_hdr==0 and len(data)==len(orig)
os.makedirs("inject_out", exist_ok=True); open(OUT,"wb").write(data)
print(f"분류: 제자리/슬랙 {st['inplace']}, redirect(완전복구) {st['redirect']}, 잘림(포인터無/풀부족) {st['trunc']}, 범위밖 {st['skip_range']}, 미번역 {st['empty']}")
print(f"풀 잔여: {sum(r[1] for r in runs):,}B")
print(f"✅ {OUT} (.text·헤더 불변, 크기불변)")
