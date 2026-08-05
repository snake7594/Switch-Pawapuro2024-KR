# -*- coding: utf-8 -*-
"""PC-relative(ADRP+ADD/LDR) 참조 검출: pcrel 대사 문자열의 명령쌍을 찾을 수 있는가."""
import struct, json, random
import numpy as np
def u32(b,o): return struct.unpack_from("<I",b,o)[0]
b=open("!exefs-작업/main-원본","rb").read()
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",b,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",b,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",b,0x30)
tx=b[tx_fo:tx_fo+tx_sz]

# 한 번에 .rodata+.data 에서 .rodata VA 범위를 가리키는 8B 값 집합 구축(4B 정렬 스캔)
def collect_ptrs(seg_fo, seg_sz):
    arr=np.frombuffer(b[seg_fo:seg_fo+seg_sz - (seg_sz%8)], dtype="<u8")
    lo,hi=ro_mo, ro_mo+ro_sz
    s=set(int(v) for v in arr[(arr>=lo)&(arr<hi)])
    # 4바이트 어긋난 포인터도 포함(half-shift)
    arr2=np.frombuffer(b[seg_fo+4:seg_fo+4+ (seg_sz-4) - ((seg_sz-4)%8)], dtype="<u8")
    s|=set(int(v) for v in arr2[(arr2>=lo)&(arr2<hi)])
    return s
ptr_set = collect_ptrs(ro_fo,ro_sz) | collect_ptrs(da_fo,da_sz)
print("문자열을 가리키는 8B 포인터(고유 VA): %d개"%len(ptr_set))

def is_adrp(w): return (w & 0x9F000000)==0x90000000
def adrp_page(w,pc):
    immlo=(w>>29)&3; immhi=(w>>5)&0x7FFFF; imm=(immhi<<2)|immlo
    if imm&(1<<20): imm-=(1<<21)
    return (pc&~0xFFF)+(imm<<12), w&0x1F
def add_imm(w):
    if (w & 0x7F800000)!=0x11000000: return None
    sh=(w>>22)&3; imm=(w>>10)&0xFFF
    if sh==1: imm<<=12
    return imm,(w>>5)&0x1F,w&0x1F
def ldr_uimm(w):
    if (w & 0xFFC00000)!=0xF9400000: return None
    imm=((w>>10)&0xFFF)*8; return imm,(w>>5)&0x1F,w&0x1F

from collections import defaultdict
page_adrps=defaultdict(list)
for off in range(0,len(tx)-3,4):
    w=u32(tx,off)
    if is_adrp(w):
        pg,rd=adrp_page(w,tx_mo+off); page_adrps[pg].append((off,rd))

def find_ref(va, window=64):
    pg=va&~0xFFF; low=va&0xFFF; hits=[]
    for aoff,rd in page_adrps.get(pg,[]):
        for d in range(1,window):
            o2=aoff+d*4
            if o2+4>len(tx): break
            w2=u32(tx,o2)
            a=add_imm(w2)
            if a and a[1]==rd and a[0]==low: hits.append((aoff,o2,"ADD")); break
            l=ldr_uimm(w2)
            if l and l[1]==rd and l[0]==low: hits.append((aoff,o2,"LDR")); break
            if (a and a[2]==rd) or (is_adrp(w2) and (w2&0x1F)==rd): break
    return hits

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
random.seed(1)
samples=[]
for s in doc["strings"]:
    if s["category"]=="exe" and s.get("has_kana") and s.get("jp_len",0)>=6:
        for o in s["occurrences"]:
            if o["method"]=="exe":
                samples.append((s["jp"], ro_mo+(o["offset"]-ro_fo))); break
    if len(samples)>=8000: break
random.shuffle(samples)
pc=[(jp,va) for jp,va in samples if va not in ptr_set][:500]
print("PC-relative 후보(포인터 집합에 없음): %d개 분석"%len(pc))

found=0; kinds={"ADD":0,"LDR":0}; ex=[]
for jp,va in pc:
    h=find_ref(va)
    if h:
        found+=1; kinds[h[0][2]]+=1
        if len(ex)<8: ex.append((jp[:18],hex(va),h[0][2],len(h)))
print("  ADRP+ADD/LDR 짝 발견: %d (%.0f%%)  유형=%s"%(found,100*found/max(len(pc),1),kinds))
with open("_pcrel_ex.txt","w",encoding="utf-8") as f:
    for e in ex: f.write("%s va=%s %s refs=%d\n"%e)
print("예시 저장 _pcrel_ex.txt")
