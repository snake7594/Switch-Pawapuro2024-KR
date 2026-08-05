# -*- coding: utf-8 -*-
"""SEN_TEXT.CHK 잘리는 선수 소개문 추출(진짜 베이스 기준 정확 예산).
   각 소개문: 진짜베이스 body에서 일본어를 NUL경계로 탐색 → 예산=텍스트+뒤 0슬랙(다음레코드 전까지, 종료NUL 1개 유지).
   현재 한글 인코딩 바이트 > 예산 인 것만 = 재번역 대상. scratchpad에 JSON 저장."""
import json, sys, os, struct, zlib
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))
SCR=r"C:\Users\JAEHOL~1\AppData\Local\Temp\claude\C--Users-Jae-Ho-Lee-Pictures-psp-roms-Breath-of-Fire-III\8090a8b2-c642-4a55-91fb-6f8b4203aba9\scratchpad"

deco,tabo,idxo,rso=R.load_rdi("RES00.RDI")
fn="SEN_TEXT.CHK"; t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc; key=R.file_key(fn)
with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
body=zlib.decompress(R.crypt(raw,key)[32:32+clen])

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
# SEN_TEXT scan 대상 jp→ko
pairs={}
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="scan" and o["file"]==fn:
            pairs[s["jp"]]=ko

def budget_for(jpb):
    """body에서 jpb(NUL경계) 위치 찾아 예산(텍스트+슬랙, 종료NUL 1개 제외) 반환. 없으면 None."""
    start=0
    while True:
        i=body.find(jpb,start)
        if i<0: return None
        pre=(i==0) or (body[i-1]==0)
        post=(i+len(jpb)>=len(body)) or (body[i+len(jpb)]==0)
        if pre and post:
            T=0; k=i+len(jpb)
            while k<len(body) and body[k]==0: T+=1; k+=1
            return len(jpb)+T-1 if T>0 else len(jpb)
        start=i+1

items=[]
for jp,ko in pairs.items():
    jpb=jp.encode("utf-8"); kob=ENC.encode(ko)
    if len(kob)<=len(jpb): continue  # 안 잘림
    bud=budget_for(jpb)
    if bud is None: continue
    if len(kob)<=bud: continue        # 슬랙으로 이미 맞음
    items.append({"jp":jp,"ko":ko,"budget_bytes":bud,
                  "cur_bytes":len(kob),"max_chars":bud//3})
items.sort(key=lambda x:-(x["cur_bytes"]-x["budget_bytes"]))
os.makedirs(SCR,exist_ok=True)
json.dump(items,open(os.path.join(SCR,"sen_recondense.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print(f"재번역 대상 {len(items)}개 (예산 초과분 큰 순).")
print("최악 5:")
for it in items[:5]:
    print(f"  예산{it['budget_bytes']}B(~{it['max_chars']}자) 현재{it['cur_bytes']}B | {it['ko'][:40]}")
print(f"저장: {os.path.join(SCR,'sen_recondense.json')}")
