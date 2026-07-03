# -*- coding: utf-8 -*-
"""NX SUR(이미지/레이아웃) CHK 안의 UI 텍스트 라벨 제자리 번역.
   REINJECT_SAFE가 NX SUR을 통째 제외해 그 안의 위젯 라벨(名前/守備位置/フォーム…)이 미번역으로 남음.
   이 라벨들은 픽셀이 아니라 '위젯 레이아웃의 NUL경계 텍스트'(게임이 렌더) → 제자리 치환 가능.
   방식: 진짜 베이스(root RDB) body에서 '사전(scan 번역) 일본어를 NUL경계로 탐색→한글(wReplace) 치환'
        (제자리, 슬랙+clean잘림, body크기 불변). 재압축 gap 적합 시 repack_out 제자리 기록, RDI decsize.
   안전: NUL양경계+유효UTF-8+사전매칭만(픽셀 오탐 거의 불가). 매칭 과다 CHK는 스킵(검토).
   대상: 인자로 받은 CHK 목록(기본=이번 스크린샷 화면들)."""
import os, sys, struct, zlib, json, bisect, re
sys.stdout.reconfigure(encoding='utf-8')
ROOT="C:/Users/Jae Ho Lee/Desktop/z/실황2024"; os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))  # 통일: tsv — 2026-07-03 폰트 단일화
OUT="repack_out"
if len(sys.argv)>=3 and sys.argv[1]=="--file":
    _all=[l.strip() for l in open(sys.argv[2],encoding="utf-8") if l.strip()]
    lo=int(sys.argv[3]) if len(sys.argv)>3 else 0
    hi=int(sys.argv[4]) if len(sys.argv)>4 else len(_all)
    TARGETS=_all[lo:hi]
else:
    TARGETS = sys.argv[1:] or ["SCS_MAKEC00.CHK","SCS_MAKEC01.CHK","SCS_ITEM.CHK","SCS_LIVE_ITEM.CHK"]
TARGETS=[t for t in TARGETS if t not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]  # 폰트 보호
jp_re=re.compile('[぀-ヿ㐀-鿿]')
ctrl_re=re.compile('[\x00-\x08\x0b-\x1f]')

dec,tab,idx,rec=R.load_rdi(os.path.join(OUT,"RES00.RDI"))
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tab:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
osz={k:os.path.getsize(k) for k in laid}
def gap_of(rdb,off):
    a=laid[rdb]; j=bisect.bisect_right(a,off)
    return (a[j] if j<len(a) else osz[rdb])-off

# 사전: 전체 번역 일본어→한글(ko≠jp) + NPB 구장 보충. (팀 구성명 ドラゴンズ 등은 exe라 전체 사용)
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
jpko={}
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko or ko==s["jp"]: continue
    jpko[s["jp"]]=ko
sup_path="npb_supplement.json"
if os.path.isfile(sup_path):
    for jp,ko in json.load(open(sup_path,encoding="utf-8")).items(): jpko[jp]=ko

def read_true(fn):
    t=idx[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,is10=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t,rdb,off,key,hdr,body

# 사전: jp(str)→kob. NUL경계 문자열 추출→조회 방식(효율·전체문자열만)
jpko_b={jp:ENC.encode(ko) for jp,ko in jpko.items() if not ctrl_re.search(jp) and len(jp)>=2}
seg_re=re.compile(rb'(?<=\x00)([^\x00]{2,80})(?=\x00)')

fh={}
try:
  for fn in TARGETS:
    if fn not in idx: print("  [RDI無]",fn); continue
    t,rdb,off,key,hdr,body=read_true(fn)
    if body.find(b"NX  SUR ")<0: print(f"  [NX SUR 아님, 건너뜀] {fn}"); continue
    buf=bytearray(body); hits=0; changed=False; matched=[]
    for m in seg_re.finditer(bytes(body)):
        seg=m.group(1)
        try: s=seg.decode("utf-8")
        except: continue
        if s in jpko_b: matched.append((m.start(1), seg, jpko_b[s], s))
    for pos,seg,kob,s in matched:
        L.patch_at_offset(buf,pos,len(seg),kob); hits+=1; changed=True
    if not changed: print(f"  [매칭0] {fn}"); continue
    if hits>400: print(f"  [매칭과다 {hits}, 검토 필요-스킵] {fn}"); continue
    assert len(buf)==len(body)
    if t["flag"]>0:
        comp=zlib.compress(bytes(buf),9); new_decsize=R.align_up(len(buf),4)
    else:
        comp=bytes(buf); new_decsize=R.align_up(32+len(buf),4)
    need=R.align_up(32+len(comp),4); g=gap_of(rdb,off)
    if need>g: print(f"  [gap부족 {need}>{g}, 스킵] {fn}"); continue
    struct.pack_into("<I",hdr,0x18,len(comp) if t["flag"]>0 else new_decsize)
    struct.pack_into("<I",hdr,0x1C,off//R.SECTOR)
    blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
    enc=R.crypt(bytes(blob),key)
    if rdb not in fh: fh[rdb]=open(os.path.join(OUT,rdb),"r+b")
    fh[rdb].seek(off); fh[rdb].write(enc)
    struct.pack_into("<I",dec,rec+t["i"]*9+4,new_decsize)
    print(f"  [OK] {fn}: 라벨 {hits}건 치환, comp {len(comp)}, decsize {new_decsize}")
finally:
    for f in fh.values(): f.close()
R.save_rdi(dec, os.path.join(OUT,"RES00.RDI"))
print("RDI 갱신. (폰트=wReplace/메인 가정 — 게임서 라벨이 정상 한글인지 확인 필요)")
