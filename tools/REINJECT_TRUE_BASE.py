# -*- coding: utf-8 -*-
"""진짜 베이스(root RDB 슬롯) 위에 한글 재주입 — 버전 불일치 근본 수정.
   원리: RES_추출원본(버전X) 기준 오프셋을 버리고, 진짜 슬롯 본문(버전Y)에서
   일본어 문자열(NUL경계)을 직접 검색해 한글로 치환(제자리, 슬랙 활용).
   대상: '크기불변·이미지없음' 텍스트 CHK (기존 유지 555 세트와 동일 기준)
   출력: repack_out RDB 제자리 갱신. RDI 변경 없음(원본 그대로 유효).
   사용: python REINJECT_TRUE_BASE.py [--limit N] (기본 전체)"""
import os, sys, struct, zlib, json
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
import inject_lib as L
RES="RES_추출원본"; OUT="repack_out"

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))

# 원본 레이아웃 (gap 검사용)
import bisect
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t0 in tabo:
    loc0=R.locate(t0["stored"],t0["flag"])
    if loc0: laid[loc0[0]].append(loc0[1])
for k0 in laid: laid[k0].sort()
orig_fs={k0:os.path.getsize(k0) for k0 in laid}
def gap_of(rdb,off):
    arr=laid[rdb]; j=bisect.bisect_right(arr,off)
    nxt=arr[j] if j<len(arr) else orig_fs[rdb]
    return nxt-off

# 대상 파일 = 기존 유지 기준(크기불변+이미지없음+변경있음)
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read(); kb=open(k,'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        targets.append(fn)
print(f"재주입 대상: {len(targets)}개")

# 파일별 (jp, ko) 쌍 수집 (scan occurrence 기준; 오프셋은 버리고 jp 텍스트만 사용)
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
per_file={}  # fn -> [(jp_bytes, ko_bytes)]
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    jpb=s["jp"].encode("utf-8")
    kob=ENC.encode(ko)
    for occ in s["occurrences"]:
        if occ["method"]=="scan" and occ["file"] in set(targets):
            per_file.setdefault(occ["file"],[]).append((jpb,kob))
# 중복 제거
for fn in per_file: per_file[fn]=list(dict.fromkeys(per_file[fn]))
print(f"jp→ko 쌍 보유 파일: {len(per_file)}")

def true_slot(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc
    key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t, rdb, off, key, hdr, body

limit=None
for a in sys.argv[1:]:
    if a.startswith("--limit"): limit=int(sys.argv[sys.argv.index(a)+1])

stats=dict(files=0, hit=0, miss=0, trunc=0)
wf={}
def revert_slot(fn):
    """대상 슬롯을 원본 RDB 바이트로 복원 (버전X 잔재 제거)."""
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc
    n=gap_of(rdb,off)
    with open(rdb,"rb") as f:
        f.seek(off); data=f.read(n)
    if rdb not in wf: wf[rdb]=open(os.path.join(OUT,rdb),"r+b")
    wf[rdb].seek(off); wf[rdb].write(data)

try:
    done=0
    for fn in targets:
        pairs=per_file.get(fn,[])
        if not pairs:
            revert_slot(fn); stats["miss"]+=1; continue
        t, rdb, off, key, hdr, body=true_slot(fn)
        buf=bytearray(body)
        changed=False
        for jpb,kob in pairs:
            # NUL 경계 매칭: jp 문자열이 NUL로 끝나는 위치 전부 치환
            start=0
            while True:
                i=buf.find(jpb,start)
                if i<0: break
                end=i+len(jpb)
                # 문자열 경계 확인: 다음 바이트가 NUL(또는 버퍼 끝)이고, 앞이 NUL/시작
                if (end>=len(buf) or buf[end]==0):
                    tr=L.patch_at_offset(buf, i, len(jpb), kob)
                    stats["trunc"]+=1 if tr else 0
                    stats["hit"]+=1; changed=True
                    start=i+max(len(kob),1)
                else:
                    start=i+1
        if not changed:
            revert_slot(fn); stats["miss"]+=1; continue
        # 새 본문 크기 동일(제자리 치환) → 재압축, decsize 불변 확인
        assert len(buf)==len(body)
        comp=zlib.compress(bytes(buf),9)
        need=R.align_up(32+len(comp),R.SECTOR)
        if need > gap_of(rdb,off):
            stats["nogap"]=stats.get("nogap",0)+1
            print(f"  [공간부족→원본복원] {fn} need={need} gap={gap_of(rdb,off)}")
            revert_slot(fn)
            continue
        struct.pack_into("<I",hdr,0x18,len(comp))
        struct.pack_into("<I",hdr,0x1C,off//R.SECTOR)
        blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
        enc=R.crypt(bytes(blob),key)
        if rdb not in wf: wf[rdb]=open(os.path.join(OUT,rdb),"r+b")
        wf[rdb].seek(off); wf[rdb].write(enc)
        stats["files"]+=1; done+=1
        if done%100==0: print(f"  {done} 파일 완료")
        if limit and done>=limit: break
finally:
    for f in wf.values(): f.close()
print(f"\n완료: 파일 {stats['files']}개, 문자열 치환 {stats['hit']}건, 파일미매칭 {stats['miss']}개, 잘림 {stats['trunc']}건")
print("RDI 불변(offset/decsize 동일). 원본 RDI 그대로 사용.")
