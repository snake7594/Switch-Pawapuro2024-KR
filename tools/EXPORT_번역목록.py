# -*- coding: utf-8 -*-
"""전체 번역 목록을 편집용 JSON으로 내보내기(일본어 원문+한국어+관련정보).
   사용자가 ko를 수정 → APPLY_번역수정.py로 번역_일본어.json에 병합(id 키) → 재주입."""
import json, sys, os
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용
doc=json.load(open("번역_일본어.json",encoding="utf-8"))

CATMAP={"text":"텍스트(CHK 대사·라벨)","name":"이름(선수·지명 등)","exe":"실행파일(대사·UI·메시지)","other":"기타"}
METMAP={"scan":"텍스트CHK","string":"STRING테이블","exe":"실행파일","nx":"이미지레이아웃라벨"}

out=[]
for s in doc["strings"]:
    methods=sorted(set(o["method"] for o in s["occurrences"]))
    files=[]
    for o in s["occurrences"]:
        fn=o.get("file","main" if o["method"]=="exe" else "")
        if fn and fn not in files: files.append(fn)
        if len(files)>=3: break
    out.append({
        "id": s["id"],
        "jp": s["jp"],
        "ko": s.get("ko",""),
        "분류": CATMAP.get(s.get("category",""), s.get("category","")),
        "사용처": [METMAP.get(m,m) for m in methods],
        "출현수": s.get("count", len(s["occurrences"])),
        "파일예": files,
    })

# NPB 구장 보충(번역_일본어.json에 없는 추가분)도 포함
sup_path="npb_supplement.json"; sup_added=0
if os.path.isfile(sup_path):
    exist={s["jp"] for s in doc["strings"]}
    nid=max(s["id"] for s in doc["strings"])+1
    for jp,ko in json.load(open(sup_path,encoding="utf-8")).items():
        if jp not in exist:
            out.append({"id":nid,"jp":jp,"ko":ko,"분류":"이름(구장 보충)","사용처":["이미지레이아웃라벨"],"출현수":0,"파일예":[]}); nid+=1; sup_added+=1

# 정렬: 분류 → 출현수 desc (자주 나오는 것 먼저)
order={"텍스트(CHK 대사·라벨)":0,"이름(선수·지명 등)":1,"실행파일(대사·UI·메시지)":2,"기타":3,"이름(구장 보충)":1}
out.sort(key=lambda x:(order.get(x["분류"],9), -x["출현수"]))

trans=sum(1 for x in out if str(x["ko"]).strip() and x["ko"]!=x["jp"])
kept =sum(1 for x in out if x["ko"]==x["jp"])
header={
 "_설명":"실황파워풀프로야구2024-2025 한글패치 전체 번역 목록입니다. 'ko'(한국어) 값을 자유롭게 수정하세요.",
 "_생성일":"2026-07-03",
 "_통계":{"총_문자열":len(out),"번역됨":trans,"원문유지(ko=jp)":kept,"구장보충추가":sup_added},
 "_필드설명":{
   "id":"고유번호(수정금지 — 재적용 키)",
   "jp":"일본어 원문(수정금지)",
   "ko":"한국어 번역 ← 여기를 수정하세요. 빈칸이거나 jp와 같으면 원문 유지됨",
   "분류":"text=CHK텍스트, name=이름, exe=실행파일(대사·UI), other=기타",
   "사용처":"번역이 들어가는 곳(텍스트CHK/STRING테이블/실행파일/이미지레이아웃라벨)",
   "출현수":"게임 내 등장 횟수(많을수록 자주 보임)",
   "파일예":"대표 CHK 파일(최대 3개)",
 },
 "_재적용방법":"ko 수정 후 이 파일을 저장하고 알려주세요. id를 키로 번역_일본어.json에 병합해 해당 문자열만 게임에 재주입합니다.",
 "_주의":"jp/id는 바꾸지 마세요. ko만 수정. 게임 폰트가 지원하는 한글만 표시됩니다(대부분 지원). 길이가 매우 길면 화면에서 잘릴 수 있습니다.",
}
res={"정보":header,"목록":out}
open("번역목록_편집용.json","w",encoding="utf-8").write(json.dumps(res,ensure_ascii=False,indent=1))
sz=os.path.getsize("번역목록_편집용.json")
print(f"생성: 번역목록_편집용.json ({sz/1e6:.1f}MB), 항목 {len(out)}개 (번역 {trans}, 원문유지 {kept}, 구장보충 {sup_added})")
print("분류별:",dict(Counter(x['분류'] for x in out)))
