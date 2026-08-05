# -*- coding: utf-8 -*-
"""exe(main NSO) 대사 확장 가능성 분석:
- .rodata zero-run 풀 용량(redirect 여유공간)
- 문자열 참조 유형 분류: 8B포인터/4B포인터(redirect 가능) vs PC-relative(ADRP/ADD, .text) vs 미발견
- ARM64 ADRP/ADD 참조 검출(.text)
"""
import struct, json, re
def u32(b,o): return struct.unpack_from("<I",b,o)[0]

b = open("!exefs-작업/main-원본","rb").read()
assert b[:4]==b"NSO0"
tx_fo,tx_mo,tx_sz = struct.unpack_from("<III",b,0x10)
ro_fo,ro_mo,ro_sz = struct.unpack_from("<III",b,0x20)
da_fo,da_mo,da_sz = struct.unpack_from("<III",b,0x30)
print(".text  fo=0x%X va=0x%X sz=0x%X"%(tx_fo,tx_mo,tx_sz))
print(".rodata fo=0x%X va=0x%X sz=0x%X"%(ro_fo,ro_mo,ro_sz))
print(".data  fo=0x%X va=0x%X sz=0x%X"%(da_fo,da_mo,da_sz))

# zero-run 풀 (.rodata)
def zero_runs(seg, base, min_len=16):
    runs=[]; i=0; n=len(seg)
    while i<n:
        if seg[i]==0:
            j=i
            while j<n and seg[j]==0: j+=1
            if j-i>=min_len: runs.append((i,j-i))
            i=j
        else: i+=1
    return runs
ro = b[ro_fo:ro_fo+ro_sz]
runs = zero_runs(ro, ro_mo, 16)
pool = sum(l for _,l in runs)
print("\n.rodata zero-run 풀(>=16B): %d개, 총 %d바이트 (%.2f MB)"%(len(runs),pool,pool/1e6))
print("  최대 run 5개:",sorted([l for _,l in runs],reverse=True)[:5])

# ADRP/ADD 인덱스: .text에서 ADRP가 만드는 페이지주소 → 그 페이지를 참조하는 명령 맵
# ADRP: bits 31=1,28-24=10000  → mask 0x9F000000 == 0x90000000
# imm = immhi(23:5)<<2 | immlo(30:29);  target_page = (PC & ~0xFFF) + (imm<<12) (signed 21bit)
tx = b[tx_fo:tx_fo+tx_sz]
def decode_adrp(word, pc_va):
    if (word & 0x9F000000) != 0x90000000: return None
    immlo=(word>>29)&3; immhi=(word>>5)&0x7FFFF
    imm=(immhi<<2)|immlo
    if imm & (1<<20): imm-=(1<<21)   # sign extend 21-bit
    return (pc_va & ~0xFFF) + (imm<<12), word & 0x1F  # (page_base, Rd)
def decode_add_imm(word):
    # ADD (immediate) 64-bit: sf=1, 0010001 shift(2) imm12(12) Rn(5) Rd(5)
    if (word & 0x7F800000) != 0x11000000: return None  # ADD imm, no shift check below
    sh=(word>>22)&3
    imm=(word>>10)&0xFFF
    if sh==1: imm<<=12
    return imm, (word>>5)&0x1F, word&0x1F  # (imm, Rn, Rd)

# .text 전체에서 ADRP가 가리키는 페이지별 명령 수집(대략) — 비용상 ADRP만 인덱싱
adrp_pages = {}  # page_base -> count
for off in range(0, len(tx)-3, 4):
    w=u32(tx,off)
    r=decode_adrp(w, tx_mo+off)
    if r: adrp_pages[r[0]] = adrp_pages.get(r[0],0)+1
print("\n.text ADRP 고유 페이지 수:",len(adrp_pages),"  ADRP 총:",sum(adrp_pages.values()))

# 샘플 대사 문자열 참조 분류
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
import random; random.seed(0)
exe_samples=[]
for s in doc["strings"]:
    if s["category"]=="exe" and s.get("has_kana") and s.get("jp_len",0)>=6:
        for o in s["occurrences"]:
            if o["method"]=="exe":
                exe_samples.append((s["jp"], o["offset"], o["len"])); break
    if len(exe_samples)>=800: break
random.shuffle(exe_samples); exe_samples=exe_samples[:500]

def find_ptr(va):
    p8=struct.pack("<Q",va); p4=struct.pack("<I",va & 0xFFFFFFFF)
    n8 = b.count(p8, ro_fo, ro_fo+ro_sz)+b.count(p8, da_fo, da_fo+da_sz)
    n4 = b.count(p4, ro_fo, ro_fo+ro_sz)+b.count(p4, da_fo, da_fo+da_sz)
    return n8,n4

cls={"ptr64":0,"ptr32":0,"pcrel_page":0,"none":0}
need_expand_examples=[]
for jp,foff,blen in exe_samples:
    va = ro_mo + (foff - ro_fo)
    n8,n4 = find_ptr(va)
    if n8>0: cls["ptr64"]+=1
    elif n4>0: cls["ptr32"]+=1
    else:
        # 같은 페이지를 ADRP가 가리키는가(=PC-relative 후보)
        if (va & ~0xFFF) in adrp_pages: cls["pcrel_page"]+=1
        else: cls["none"]+=1

print("\n=== 대사 문자열 참조 유형(샘플 %d개) ==="%len(exe_samples))
for k,v in cls.items(): print("  %-12s %d (%.0f%%)"%(k,v,100*v/len(exe_samples)))
print("\n해석: ptr64/ptr32 = redirect 가능(포인터만 교체). pcrel_page = .text ADRP/ADD 직접참조(명령 패치 필요).")
print("      none = 포인터·ADRP페이지 모두 미발견(다른 방식 참조 or 미사용).")
