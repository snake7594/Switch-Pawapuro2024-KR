# -*- coding: utf-8 -*-
"""555개 유지(한글) CHK의 낡은베이스 감사:
   repack_in 본문 vs 실제 원본RDB 슬롯 본문의 차이를
   (a) 번역 JSON의 스캔 오프셋(=의도된 텍스트 패치)과 (b) 그 외(=낡은베이스 오염)로 분류."""
import os, sys, struct, zlib, json
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")

# 유지 555 목록 재계산 (FINALIZE_CLEAN2와 동일 기준)
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
kept=[]
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read(); kb=open(k,'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        kept.append(fn)
print(f"유지 대상: {len(kept)}개")

# 번역 JSON에서 파일별 의도된 스캔 패치 오프셋 수집
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
intended={}  # fn -> [(off,len)]
for s in doc["strings"]:
    if not str(s.get("ko","")).strip(): continue
    for occ in s["occurrences"]:
        if occ["method"]=="scan":
            intended.setdefault(occ["file"],[]).append((occ["offset"],occ["len"]))
print(f"스캔 패치 의도 파일 수: {len(intended)}")

def true_body(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"])
    if loc is None: return None
    rdb,off,_=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    return zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])

def diff_regions(x,y):
    rs=[]; i=0; N=min(len(x),len(y))
    while i<N:
        if x[i]!=y[i]:
            j=i
            while j<N and x[j]!=y[j]: j+=1
            rs.append((i,j)); i=j
        else: i+=1
    return rs

# 의도영역: 오프셋~오프셋+len+슬랙(뒤 NUL런). 넉넉히 +64 마진
def in_intended(fn, s, e, base):
    for off,ln in intended.get(fn,[]):
        # 슬랙 포함 영역 [off, off+ln+T]. T: 원본 base의 NUL런
        k=off+ln; T=0
        while k<len(base) and base[k]==0: T+=1; k+=1
        if s>=off and e<=off+ln+T: return True
    return False

bad=[]; clean=0; checked=0
for fn in kept:
    tb=true_body(fn)
    if tb is None: continue
    kb=open(os.path.join("repack_in",fn),'rb').read()[32:]
    if len(tb)!=len(kb):
        bad.append((fn,'크기다름',len(tb),len(kb))); continue
    rs=diff_regions(tb,kb)
    stale=[ (s,e) for s,e in rs if not in_intended(fn,s,e,tb) ]
    checked+=1
    if stale:
        bad.append((fn,'비의도변경',len(stale),sum(e-s for s,e in stale)))
    else:
        clean+=1
    if checked%100==0: print(f"  진행 {checked}/{len(kept)}")

print(f"\n검사 {checked}개: 깨끗(텍스트만) {clean}개, 오염 {len(bad)}개")
for item in bad[:30]:
    print("  ", item)
json.dump([b[0] for b in bad], open("_stale_files.json","w",encoding="utf-8"), ensure_ascii=False)
print("오염 목록 → _stale_files.json")
