# -*- coding: utf-8 -*-
"""main-원본의 문자열 참조 분석 → exe 번역후보 중 '참조 안 됨(구조데이터 오추출 의심)' 분류.
   참조 = (A) ro/data의 8B 포인터가 그 VA를 가리킴  OR  (B) .text의 ADRP(+ADD/LDR)가 그 VA를 계산.
   참조 안 되는 문자열은 진짜 문자열이 아닐 확률 높음(점프테이블/부동소수/포인터 조각) → 번역 제외 대상."""
import sys, struct, json, os
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용

b=open("!exefs-작업/main-원본","rb").read()
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",b,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",b,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",b,0x30)
ro_lo,ro_hi=ro_mo,ro_mo+ro_sz
print(f".text VA[0x{tx_mo:x},0x{tx_mo+tx_sz:x}) .rodata VA[0x{ro_lo:x},0x{ro_hi:x}) .data VA[0x{da_mo:x},0x{da_mo+da_sz:x})")

# (A) 데이터 포인터 (ro+data의 8B 워드값이 .rodata 범위)
refs=set()
for seg_fo,seg_sz in [(ro_fo,ro_sz),(da_fo,da_sz)]:
    for shift in (0,4):
        base=seg_fo+shift; n=(seg_sz-shift)//8
        arr=np.frombuffer(b[base:base+n*8],dtype="<u8")
        hit=arr[(arr>=ro_lo)&(arr<ro_hi)]
        refs.update(int(x) for x in hit)
print(f"(A) 데이터포인터가 가리키는 .rodata VA: {len(refs)}개")

# (B) 코드 ADRP(+ADD/LDR) 참조 (비트마스크, numpy)
code=np.frombuffer(b[tx_fo:tx_fo+ (tx_sz//4)*4], dtype="<u4")
is_adrp=(code & 0x9F000000)==0x90000000
adrp_idx=np.nonzero(is_adrp)[0]
print(f"ADRP 명령: {len(adrp_idx)}개, 후속 ADD/LDR 매칭 중...")
def adrp_page(w, va):
    immlo=(w>>29)&3; immhi=(w>>5)&0x7ffff
    imm=(immhi<<2)|immlo
    if imm & (1<<20): imm-=(1<<21)  # sign extend 21bit
    return (va & ~0xFFF) + (imm<<12)
codrefs=set()
W=code
for i in adrp_idx:
    w=int(W[i]); rd=w & 0x1f
    va=tx_mo + int(i)*4
    page=adrp_page(w, va)
    # 다음 1~5 명령에서 ADD/LDR (Rn==rd) 찾기
    for j in range(i+1, min(i+6, len(W))):
        w2=int(W[j])
        # ADD imm (64b): (w&0x7F800000)==0x11000000
        if (w2 & 0x7F800000)==0x11000000:
            rn=(w2>>5)&0x1f; rd2=w2&0x1f
            if rn==rd:
                sh=(w2>>22)&1; imm12=(w2>>10)&0xfff
                off=imm12<<(12 if sh else 0)
                t=page+off
                if ro_lo<=t<ro_hi: codrefs.add(t)
                break
        # LDR imm unsigned (64b): (w&0xFFC00000)==0xF9400000
        if (w2 & 0xFFC00000)==0xF9400000:
            rn=(w2>>5)&0x1f
            if rn==rd:
                imm12=(w2>>10)&0xfff; t=page+imm12*8
                # LDR로 로드하는 주소 자체가 포인터일 수 있음 → 그 VA도 참조로
                if ro_lo<=t<ro_hi: codrefs.add(t)
                break
print(f"(B) 코드가 계산하는 .rodata VA: {len(codrefs)}개")

allrefs=refs|codrefs
print(f"참조 VA 합집합: {len(allrefs)}개")

# exe 번역 후보 로드 + 분류
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
cand=[]  # (va, off, len, jp, ko)
for s in doc["strings"]:
    for o in s["occurrences"]:
        if o["method"]=="exe":
            off=o["offset"]; va=ro_mo+(off-ro_fo)
            cand.append((va, off, o["len"], s["jp"], s.get("ko","").strip()))
print(f"\nexe 번역 occurrence: {len(cand)}개")
ref_c=[c for c in cand if c[0] in allrefs]
unref=[c for c in cand if c[0] not in allrefs]
print(f"  참조됨(안전): {len(ref_c)}")
print(f"  ★참조안됨(구조데이터 의심, 제외후보): {len(unref)}")
print("\n참조안됨 샘플 20:")
for va,off,ln,jp,ko in unref[:20]:
    print(f"  VA0x{va:x} len={ln} jp={jp[:24]!r}")
# 참조안됨 저장
json.dump([c[1] for c in unref], open("_exe_unref_offsets.json","w"), )
print(f"\n참조안됨 오프셋 목록 → _exe_unref_offsets.json ({len(unref)}개)")
