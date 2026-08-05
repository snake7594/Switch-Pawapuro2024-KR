# -*- coding: utf-8 -*-
"""수정한 번역목록(편집용/분할)을 번역_일본어.json에 병합(id 키). 변경된 ko만 반영.
   사용: python APPLY_번역수정.py 번역목록_편집용.json   (또는 번역목록_분할/번역_이름.json 등, 여러개 가능)
   병합 후 재주입(REINJECT_SAFE / NXSUR_LABEL_INJECT / SEN_ROSTER_SLACK / FINALIZE_EXE_SAFE3 등) 필요."""
import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용
if len(sys.argv)<2:
    print("사용: python APPLY_번역수정.py <수정한 json> [추가 json ...]"); sys.exit(1)

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
byid={s["id"]:s for s in doc["strings"]}
changed=0; unknown=0; samples=[]
for path in sys.argv[1:]:
    edited=json.load(open(path,encoding="utf-8"))
    items=edited["목록"] if isinstance(edited,dict) and "목록" in edited else edited
    for x in items:
        i=x.get("id"); ko=str(x.get("ko",""))
        if i is None: continue
        s=byid.get(i)
        if s is None: unknown+=1; continue
        if str(s.get("ko",""))!=ko:
            if len(samples)<15: samples.append((s["jp"][:16], s.get("ko","")[:16], ko[:16]))
            s["ko"]=ko; changed+=1

json.dump(doc,open("번역_일본어.json","w",encoding="utf-8"),ensure_ascii=False)
print(f"병합 완료: 변경 {changed}건, 알수없는 id {unknown}건")
for jp,old,new in samples: print(f"  {jp!r}: {old!r} → {new!r}")
print("다음: 변경된 문자열의 사용처에 맞게 재주입 실행 (README_번역편집.md 참고).")
