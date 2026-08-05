# -*- coding: utf-8 -*-
"""exe 추가 제자리 주입 — 추출 누락 UI 라벨 복구(garbling 해결).
   원인: 추출이 '데이터포인터 참조' 문자열만 잡아, 코드참조(ADRP+ADD)로만 쓰이는 UI 라벨(決定/投手/先発…)이
   누락→미번역→ADD폰트가 한자셀을 한글로 덮어써 garbled 한글로 렌더.
   해결: main-safe2(이미 170,450 제자리 패치본)를 base로, .rodata의 '미추출 일본어 완전문자열' 중
         사전(jp→ko)에 번역있는 것(2글자+·제어바이트X)을 제자리 치환(tsv/ADD 인코딩, 슬랙+clean잘림).
   제자리만(포인터 재작성·풀·이동 0) → 크래시 무관. .text·.data·헤더 불변 검증. 출력 main-safe3."""
import os, sys, struct, json, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용; sys.path.insert(0,".")
import inject_lib as L
import numpy as np
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))  # exe=ADD폰트(가→亜)
ORIG="!exefs-작업/main-원본"; BASE="inject_out/main-safe2"; OUT="inject_out/main-safe3"

o=open(ORIG,"rb").read()
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",o,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",o,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",o,0x30)
ro=o[ro_fo:ro_fo+ro_sz]
jp_re=re.compile('[぀-ヿ㐀-鿿]')
ctrl_re=re.compile('[\x00-\x08\x0b-\x1f]')

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
exe_off=set(); jpko={}
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if ko and ko!=s["jp"]: jpko[s["jp"]]=ko
    for oc in s["occurrences"]:
        if oc["method"]=="exe": exe_off.add(oc["offset"])

# .rodata에서 미추출 일본어 완전문자열 → 사전 번역있는 것만
missed=[]; i=0; N=len(ro)
while i<N:
    if ro[i]==0: i+=1; continue
    j=ro.find(b"\x00",i)
    if j<0: j=N
    try: s=ro[i:j].decode("utf-8")
    except: i=j+1; continue
    if jp_re.search(s) and (ro_fo+i) not in exe_off and not ctrl_re.search(s) and len(s)>=2 and s in jpko:
        missed.append((ro_fo+i, s, jpko[s]))
    i=j+1
print(f"복구 대상(미추출·번역有): {len(missed)}건")

base=bytearray(open(BASE,"rb").read())
st=dict(fit=0,mild=0,skip_heavy=0)
skipped=[]
for off,jp,ko in missed:
    jl=len(jp.encode("utf-8")); kob=ENC.encode(ko)
    # 슬랙 cap
    T=0; k=off+jl
    while k<len(base) and base[k]==0: T+=1; k+=1
    cap=jl+T-1 if T>0 else jl
    if len(kob)<=cap:
        L.patch_at_offset(base, off, jl, kob); st["fit"]+=1
    elif len(kob)-cap<=3:   # 1음절 이하 손실 = 경미 UI 라벨, 허용
        L.patch_at_offset(base, off, jl, kob); st["mild"]+=1
    else:                    # 중잘림(대부분 이름) = 새 잘림 방지 위해 스킵(나중 redirect)
        st["skip_heavy"]+=1; skipped.append((jp,ko))

# 안전 검증: main-원본 대비 .text·.data·헤더 불변(=in-place .rodata만)
an=np.frombuffer(bytes(base),dtype=np.uint8); ao=np.frombuffer(o,dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
in_tx=int(((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum())
in_da=int(((diff>=da_fo)&(diff<da_fo+da_sz)).sum())
in_hdr=int((diff<0x100).sum())
print(f"main-원본 대비 변경 {len(diff):,}B: .text={in_tx} .data={in_da} 헤더={in_hdr}")
assert in_tx==0 and in_da==0 and in_hdr==0 and len(base)==len(o), "안전 위반!"
open(OUT,"wb").write(base)
print(f"딱맞음 {st['fit']}, 경미손실허용 {st['mild']}, 중잘림스킵(이름류) {st['skip_heavy']}")
print(f"✅ {OUT} — main-safe2 + 미추출 UI라벨 {st['fit']+st['mild']}건 제자리 패치(.text/.data/헤더 불변)")
import json as J
J.dump(skipped, open(os.path.join(os.environ.get('TEMP','.'),'exe_skipped_names.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"  스킵된 중잘림(이름류) {len(skipped)}건 → 나중 안전 redirect 대상")
