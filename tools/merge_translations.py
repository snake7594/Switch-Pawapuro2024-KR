# -*- coding: utf-8 -*-
"""번역 배치 결과(batch_NNNN_ko.json)를 번역_일본어.json 의 ko 에 병합.
- 각 배치 입력 id 집합과 출력 id 비교 → 누락/실패 배치 보고(재실행용).
- 제어태그 보존 간이 검증(번역문이 jp의 %s/<...> 토큰 수를 유지하는지).
- 병합 후 finalize_jp_json.py 다시 돌리면 분리본 갱신.
"""
import json, os, glob, re
DIR = "translate_batches"
TOK = re.compile(r"%[0-9.]*[sdufxX]|<[^>]{1,20}>")

def load_lenient(path):
    """에이전트가 쓴 _ko.json 관대 파싱: 마크다운 펜스 제거 + 제어문자 허용(strict=False)."""
    t = open(path, encoding="utf-8").read().strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"): t = t.rstrip()[:-3]
    # 첫 '[' ~ 마지막 ']' 로 잘라 본문만(앞뒤 잡텍스트 제거)
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j != -1 and j > i: t = t[i:j+1]
    return json.loads(t, strict=False)

doc = json.load(open("번역_일본어.json", encoding="utf-8"))
by_id = {s["id"]: s for s in doc["strings"]}

ko_map = {}
bad_batches = []
tok_warn = 0
n_batches = len(glob.glob(os.path.join(DIR, "batch_*.json"))) - len(glob.glob(os.path.join(DIR, "batch_*_ko.json")))
inputs = sorted(glob.glob(os.path.join(DIR, "batch_[0-9][0-9][0-9][0-9].json")))
for inp in inputs:
    base = inp[:-5]  # strip .json
    outp = base + "_ko.json"
    try:
        in_items = json.load(open(inp, encoding="utf-8"))
    except Exception:
        continue
    in_ids = {it["id"] for it in in_items}
    if not os.path.isfile(outp):
        bad_batches.append((os.path.basename(base), "MISSING", len(in_ids))); continue
    try:
        out_items = load_lenient(outp)
    except Exception as e:
        bad_batches.append((os.path.basename(base), "BADJSON", str(e)[:40])); continue
    got = {}
    for it in out_items:
        if isinstance(it, dict) and "id" in it and "ko" in it and isinstance(it["ko"], str):
            got[it["id"]] = it["ko"]
    missing = in_ids - set(got)
    if missing:
        bad_batches.append((os.path.basename(base), "PARTIAL", len(missing)))
    for i, ko in got.items():
        if i in by_id:
            jp = by_id[i]["jp"]
            # 제어태그 수 보존 간이검증
            if sorted(TOK.findall(jp)) != sorted(TOK.findall(ko)):
                tok_warn += 1
            ko_map[i] = ko

# 적용
applied = 0
for i, ko in ko_map.items():
    if by_id[i].get("ko", "") != ko:
        by_id[i]["ko"] = ko; applied += 1
json.dump(doc, open("번역_일본어.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

total = len(doc["strings"])
translated = sum(1 for s in doc["strings"] if s.get("ko", "").strip())
print("=" * 60)
print("병합: 적용 %d개, 누적 번역 %d/%d (%.1f%%)" % (applied, translated, total, 100*translated/total))
print("제어태그 불일치 경고: %d개 (수동 확인 권장)" % tok_warn)
print("문제 배치 %d개 (재실행 필요):" % len(bad_batches))
for b in bad_batches[:30]: print("  ", b)
if len(bad_batches) > 30: print("   ... 외 %d개" % (len(bad_batches)-30))
print("=" * 60)
print("다음: 미번역 남으면 split_for_translate.py 재실행→워크플로 재실행, 아니면 finalize_jp_json.py")
