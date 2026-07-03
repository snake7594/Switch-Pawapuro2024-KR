# -*- coding: utf-8 -*-
"""main-safe4(nso)에 추가 exe 패치 → main-safe5.
- 순한자 신규 번역(_kanji_translations.json: [{i,ko}]) 주입 (offs=_exe_순한자_번역대상.json)
- middot ·→・ 등 기주입 exe 문자열 재주입 (번역_일본어.json exe occurrences, ko에 ・/ー 반영)
동적 현재길이(오프셋~NUL) 사용 → 미주입(일본어)/기주입(한글) 모두 안전.
초과 시 patch_at_offset이 UTF-8 안전 절단."""
import json, sys, os
import inject_lib as L
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")

SRC = "inject_out/main-safe4"
DST = "inject_out/main-safe5"
ENC_EXE = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv"))

buf = bytearray(open(SRC, "rb").read())
print(f"src {SRC} len={len(buf)}")

def cur_len(off):
    e = buf.find(b"\x00", off)
    return e - off if e >= 0 else 0

patched = 0; trunc = 0; miss = set(); skipped = 0

# ---- 1) 순한자 신규 번역 ----
tgt = json.load(open("_exe_순한자_번역대상.json", encoding="utf-8"))  # [{jp,offs,blen,budget,syl}]
tr  = json.load(open("_kanji_translations.json", encoding="utf-8"))   # [{i,ko}]
ko_by_i = {r["i"]: (r.get("ko") or "").strip() for r in tr}
for i, item in enumerate(tgt):
    ko = ko_by_i.get(i, "")
    if not ko:
        skipped += 1; continue
    miss.update(ENC_EXE.covers(ko))
    budget = item["budget"]
    kob = ENC_EXE.encode(ko)
    if len(kob) > budget and " " in ko:          # 초과 시 공백 제거 폴백(절단 최소화)
        kob2 = ENC_EXE.encode(ko.replace(" ", ""))
        if len(kob2) <= budget: kob = kob2
    for off in item["offs"]:
        ol = cur_len(off)
        if ol == 0: continue
        if L.patch_at_offset(buf, off, ol, kob): trunc += 1
        patched += 1
print(f"[순한자] 패치 {patched} occ, 스킵(빈번역) {skipped}, 절단 {trunc}")

# ---- 2) 기주입 exe 문자열 재주입: (a) 현재바이트가 깨진 UTF-8(dangling→ID누출) (b) middot ・/ー ----
def cur_bytes(off):
    e = buf.find(b"\x00", off)
    return bytes(buf[off:e]) if e >= 0 else b""
def is_broken(bs):
    try: bs.decode("utf-8"); return False
    except UnicodeDecodeError: return True
doc = json.load(open("번역_일본어.json", encoding="utf-8"))
p2 = 0; t2 = 0; dangle = 0; midf = 0
for s in doc["strings"]:
    ko = s.get("ko", "").strip()
    if not ko: continue
    has_mid = ("・" in ko) or ("ー" in ko)
    kob = ENC_EXE.encode(ko)
    for o in s.get("occurrences", []):
        if o["method"] != "exe": continue
        off = o["offset"]
        cb = cur_bytes(off)
        broken = is_broken(cb)
        if not broken and not has_mid: continue   # 정상+미들닷아님 → 건드리지 않음
        if broken: dangle += 1
        elif has_mid: midf += 1
        miss.update(ENC_EXE.covers(ko))
        ol = len(cb)
        if L.patch_at_offset(buf, off, ol, kob): t2 += 1
        p2 += 1
print(f"[재주입] {p2} occ (dangling수리 {dangle}, middot {midf}), 절단 {t2}")

open(DST, "wb").write(buf)
print(f"저장 {DST} len={len(buf)}")
if miss: print(f"[!] 폰트 미지원 한글 {len(miss)}종: {''.join(sorted(miss))[:60]}")
