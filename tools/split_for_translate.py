# -*- coding: utf-8 -*-
"""번역_일본어.json → 번역 배치 파일들(translate_batches/batch_NNNN.json).
- ko 가 비어 있는 문자열만 배치(재실행 시 이미 번역된 건 제외 = 이어하기).
- 각 배치 = [{id, category, jp}] (BATCH개씩).
"""
import json, os, math
BATCH = 250
doc = json.load(open("번역_일본어.json", encoding="utf-8"))
todo = [s for s in doc["strings"] if not s.get("ko", "").strip()]
os.makedirs("translate_batches", exist_ok=True)
n = 0
for i in range(0, len(todo), BATCH):
    chunk = todo[i:i+BATCH]
    out = [{"id": s["id"], "category": s["category"], "jp": s["jp"]} for s in chunk]
    json.dump(out, open(f"translate_batches/batch_{n:04d}.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    n += 1
print("미번역 %d개 → 배치 %d개 (batch=%d), translate_batches/" % (len(todo), n, BATCH))
print("BATCH_COUNT=%d" % n)
