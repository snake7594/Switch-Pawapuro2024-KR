# -*- coding: utf-8 -*-
"""번역_일본어.json 보강 + 카테고리별 분리.
- 각 문자열에 has_kana(가나 포함=확실한 일본어 문장), jp_len(문자수) 추가
- 카테고리별 파일 분리: 대사(text) / 이름(name) / 기타(other)
- 번역 우선순위용 '대사_가나포함_2자이상' 통계
"""
import json, re
KANA = re.compile("[぀-ヿｦ-ﾟ]")
d = json.load(open("번역_일본어.json", encoding="utf-8"))
for s in d["strings"]:
    s["has_kana"] = bool(KANA.search(s["jp"]))
    s["jp_len"] = len(s["jp"])
# 재저장(보강된 메인)
json.dump(d, open("번역_일본어.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 카테고리별 분리
buckets = {"text": [], "name": [], "other": [], "exe": []}
for s in d["strings"]:
    buckets.get(s["category"], buckets["other"]).append(s)
names = {"text": "번역_일본어_대사.json", "name": "번역_일본어_이름.json",
         "other": "번역_일본어_기타.json", "exe": "번역_일본어_실행파일.json"}
for cat, arr in buckets.items():
    # id 재부여
    for i, s in enumerate(arr, 1): s["local_id"] = i
    json.dump({"meta": {"category": cat, "count": len(arr),
                        "source": d["meta"]["source"]}, "strings": arr},
              open(names[cat], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

dialogue = [s for s in buckets["text"] if s["has_kana"] and s["jp_len"] >= 2]
print("총 고유:", len(d["strings"]))
print("카테고리:", {k: len(v) for k, v in buckets.items()})
print("대사 중 가나포함·2자이상(우선 번역대상):", len(dialogue))
print("파일:", "번역_일본어.json(전체) + 대사/이름/기타 분리본")
