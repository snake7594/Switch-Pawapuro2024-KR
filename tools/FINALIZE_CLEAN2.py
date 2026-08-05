# -*- coding: utf-8 -*-
"""완전 청정 빌드:
   유지 대상 M = 폰트B 2개 + '크기불변·이미지없음' 텍스트 스캔 CHK (한글)
   그 외 repack_in의 모든 CHK(STRING 재구성 43·이미지 1754 등) → 원본 슬롯 바이트 복사로 복원
   RDI = 원본 파일 그대로 (변수 제거)
   최종: repack_out = 원본 RDB + M 슬롯만 제자리 교체, RDI 원본."""
import os, sys, struct, shutil, bisect
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"; OUT="repack_out"

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")

# 원본 레이아웃
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tabo:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
orig_fs={k:os.path.getsize(k) for k in laid}
def next_off(rdb,off):
    arr=laid[rdb]; j=bisect.bisect_right(arr,off)
    return arr[j] if j<len(arr) else orig_fs[rdb]

# M(유지) 분류
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK")]
keep=set(["COMMON_2D.CHK","COMMON_2D_ADD.CHK"])
revert=[]
for fn in files:
    if fn in keep: continue
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read()
    kb=open(k,'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        keep.add(fn)          # 크기불변+이미지없음+한글 → 유지
    elif ob==kb:
        pass                  # 무변경 — repack이 원본재기록했어도 내용동일
    else:
        revert.append(fn)     # STRING 재구성/이미지/기타 → 원본 복원
print(f"유지(한글) M: {len(keep)}개 (폰트2 + 텍스트 {len(keep)-2})")
print(f"원본 복원 대상: {len(revert)}개")

# 원본 슬롯 바이트 복사
rf={rdb: open(rdb,"rb") for rdb in laid}
wf={rdb: open(os.path.join(OUT,rdb),"r+b") for rdb in laid}
CH=8*1024*1024
try:
    done=0; total=0
    for fn in revert:
        t=idxo[fn]; loc=R.locate(t["stored"],t["flag"])
        if loc is None: continue
        rdb,off,is10=loc
        n=next_off(rdb,off)-off
        rf[rdb].seek(off); wf[rdb].seek(off)
        remain=n
        while remain>0:
            c=rf[rdb].read(min(CH,remain))
            if not c: break
            wf[rdb].write(c); remain-=len(c)
        total+=n; done+=1
        if done%300==0: print(f"  {done}/{len(revert)} ({total/1e6:.0f}MB)")
finally:
    for f in rf.values(): f.close()
    for f in wf.values(): f.close()
print(f"복원 완료: {done}개, {total/1e6:.0f}MB")

# RDI = 원본
shutil.copy2("RES00.RDI", os.path.join(OUT,"RES00.RDI"))
print("RDI: 원본 복사")

# 검증
import zlib
def read_body(arc, base_dir):
    t=idxo[arc]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc
    p=os.path.join(base_dir,rdb) if base_dir else rdb
    key=R.file_key(arc)
    with open(p,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(p,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    return zlib.decompress(d[32:32+clen]) if t["flag"]>0 else d[32:]

print("\n=== 검증 ===")
ok=True
for arc in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK"):
    got=read_body(arc,OUT); src=open(os.path.join("repack_in",arc),"rb").read()[32:]
    g= got==src; ok&=g
    print(f"  폰트 {arc}: {'OK' if g else '불일치!'}")
# 유지 텍스트 샘플 3
sample=[f for f in sorted(keep) if f not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")][:3]
for fn in sample:
    got=read_body(fn,OUT); src=open(os.path.join("repack_in",fn),"rb").read()[32:]
    g= got==src; ok&=g
    print(f"  한글유지 {fn}: {'OK' if g else '불일치!'}")
# 복원 샘플 3
for fn in revert[:3]:
    got=read_body(fn,OUT); src=open(os.path.join(RES,fn),"rb").read()[32:]
    g= got[:len(src)]==src; ok&=g
    print(f"  원본복원 {fn}: {'OK' if g else '불일치!'}")
print("전체:", "통과" if ok else "실패!")
print("\nrepack_out = 원본RDB + 폰트B + 텍스트한글(크기불변). RDI=원본. 스톡 main과 테스트.")
