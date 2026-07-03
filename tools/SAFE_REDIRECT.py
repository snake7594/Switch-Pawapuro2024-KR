# -*- coding: utf-8 -*-
"""exe 대사/문구 잘림 안전 복구 — '진짜 죽은 zero-run 풀'로 redirect.
   이전 크래시 원인(main-final): 풀이 zero-run을 free로 썼으나 데이터포인터 12,841개가 그 안을 가리켜 clobber.
   여기선 풀에서 다음을 전부 배제 → 아무도(데이터·코드) 참조 안 하는 바이트만 사용:
     (1) 데이터포인터 타겟(8정렬 .rodata/.data 워드값이 .rodata VA)이 내부에 있는 run
     (2) ADRP 또는 ADR 로 코드가 가리키는 .rodata 페이지/주소가 걸치는 run
     (3) run 양끝 32B 예약(선행 문자열 종료자·후행 경계 보호), run>=64B만
   각 '제자리에서 잘렸던 exe 문자열' 중 데이터포인터 있는 것 → 풀에 전체 한글 기록 + 그 포인터들을 풀 VA로 교체.
   제자리(잘린) 사본은 유지(코드참조 경로) → 데이터포인터 경로는 전체 한글.
   base=main-safe3. 검증: .text·헤더 불변, 풀 기록이 죽은바이트 내, 포인터교체만. 출력 main-safe4."""
import os, sys, struct, json
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
os.chdir("C:/Users/Jae Ho Lee/Desktop/z/실황2024"); sys.path.insert(0,".")
import inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))
ORIG="!exefs-작업/main-원본"; BASE="inject_out/main-safe3"; OUT="inject_out/main-safe4"

data=bytearray(open(BASE,"rb").read()); orig=bytes(open(ORIG,"rb").read())
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",data,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",data,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",data,0x30)
ro_lo,ro_hi=ro_mo,ro_mo+ro_sz

# ---- pidx: VA -> [pointer 위치들] (8정렬 .rodata/.data 워드값이 .rodata VA) ----
pidx=defaultdict(list); tgt=set()
for seg_fo,seg_sz in [(ro_fo,ro_sz),(da_fo,da_sz)]:
    n=seg_sz//8
    arr=np.frombuffer(bytes(data[seg_fo:seg_fo+n*8]),dtype="<u8")
    for i in np.nonzero((arr>=ro_lo)&(arr<ro_hi))[0]:
        v=int(arr[i]); pidx[v].append(seg_fo+int(i)*8); tgt.add(v)
tgt_sorted=np.array(sorted(tgt),dtype="<u8")

# ---- 코드참조 .rodata 주소: ADRP(페이지) + ADR(정확주소) ----
txt=np.frombuffer(orig[tx_fo:tx_fo+(tx_sz//4)*4],dtype="<u4")
code_pages=set(); adr_addrs=set()
top=(txt & np.uint32(0x1F000000))
adrp_mask=(txt & np.uint32(0x9F000000))==np.uint32(0x90000000)
adr_mask =(txt & np.uint32(0x9F000000))==np.uint32(0x10000000)
for i in np.nonzero(adrp_mask)[0]:
    w=int(txt[i]); pc=tx_mo+int(i)*4
    imm=(((w>>5)&0x7FFFF)<<2)|((w>>29)&3)
    if imm&(1<<20): imm-=(1<<21)
    tp=((pc>>12)<<12)+(imm<<12)
    if ro_lo-0x1000<=tp<ro_hi: code_pages.add(tp>>12)
for i in np.nonzero(adr_mask)[0]:
    w=int(txt[i]); pc=tx_mo+int(i)*4
    imm=(((w>>5)&0x7FFFF)<<2)|((w>>29)&3)
    if imm&(1<<20): imm-=(1<<21)
    ta=pc+imm
    if ro_lo<=ta<ro_hi: adr_addrs.add(ta>>12)  # 페이지 단위 배제(보수)
code_pages|=adr_addrs

# ---- 안전 풀: 죽은 zero-run ----
RES=32; MINRUN=64
runs=[]; i=0
while i<ro_sz:
    if data[ro_fo+i]==0:
        j=i
        while j<ro_sz and data[ro_fo+j]==0: j+=1
        if j-i>=MINRUN:
            s_va=ro_mo+i; e_va=ro_mo+j
            lo=int(np.searchsorted(tgt_sorted,s_va)); hi=int(np.searchsorted(tgt_sorted,e_va))
            has_ptr= hi>lo
            has_code=any((p in code_pages) for p in range(s_va>>12,((e_va-1)>>12)+1))
            if not has_ptr and not has_code:
                runs.append([i+RES, (j-RES)-(i+RES)])  # 양끝 RES 예약
        i=j
    else: i+=1
runs=[r for r in runs if r[1]>=8]
runs.sort(key=lambda r:-r[1])
pool_total=sum(r[1] for r in runs)
print(f"안전 풀 {len(runs)} runs, {pool_total:,}B")
def alloc(need):
    for r in runs:
        if r[1]>=need:
            pos=r[0]; r[0]+=need; r[1]-=need; return pos
    return None

def cap_of(off,ln):
    T=0;k=off+ln
    while k<len(orig) and orig[k]==0: T+=1;k+=1
    return ln+T-1 if T>0 else ln

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
st=defaultdict(int)
for s in doc["strings"]:
    ko=s.get("ko","").strip()
    if not ko: continue
    kob=ENC.encode(ko)
    for occ in s["occurrences"]:
        if occ["method"]!="exe": continue
        off=occ["offset"]; ln=occ["len"]
        if off<ro_fo or off+ln>ro_fo+ro_sz: continue
        if len(kob)<=cap_of(off,ln): continue   # 제자리로 이미 맞음
        va=ro_mo+(off-ro_fo)
        locs=pidx.get(va,[])
        if not locs: st["noptr"]+=1; continue    # 포인터無 → 제자리 잘림 유지
        pos=alloc(len(kob)+1)
        if pos is None: st["poolfull"]+=1; continue
        nfo=ro_fo+pos; nva=ro_mo+pos
        data[nfo:nfo+len(kob)]=kob; data[nfo+len(kob)]=0
        for loc in locs: struct.pack_into("<Q",data,loc,nva)
        st["redirect"]+=1

# ---- 안전 검증 ----
an=np.frombuffer(bytes(data),dtype=np.uint8); ao=np.frombuffer(orig,dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
in_tx=int(((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum())
in_hdr=int((diff<0x100).sum())
print(f"main-원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr} (0이어야 함)")
assert in_tx==0 and in_hdr==0 and len(data)==len(orig)
open(OUT,"wb").write(data)
print(f"redirect(전체복구) {st['redirect']}, 포인터無잘림유지 {st['noptr']}, 풀부족 {st['poolfull']}")
print(f"✅ {OUT} — 죽은풀 redirect(.text·헤더 불변)")
