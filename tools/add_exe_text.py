# -*- coding: utf-8 -*-
"""main 실행파일(NSO)의 일본어를 추출해 번역_일본어.json 에 병합.
- 소스: !exefs-작업/main-원본 (원본 NSO0, 비압축)
- .rodata 세그먼트만 0x00-split UTF-8 + 가나게이트 + 제어문자 제외(품질필터)
- 기존 JSON과 동일 텍스트는 occurrence 추가, 신규는 category=exe
- file="main", method="exe", offset=main파일 절대오프셋, len=바이트길이
실행 후 finalize_jp_json.py 를 다시 돌리면 has_kana/jp_len/분리본 갱신됨.
"""
import os, re, json, struct
from collections import defaultdict

EXE = os.path.join("!exefs-작업", "main-원본")
JSONF = "번역_일본어.json"

KANA = re.compile(rb"\xe3[\x81-\x83]|\xef\xbd[\xa6-\xbf]|\xef\xbe[\x80-\x9d]")
JP   = re.compile("[぀-ゟ゠-ヿㇰ-ㇿ㐀-䶿一-鿿豈-﫿ｦ-ﾝ々〆〇〻]")
CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")  # \t,\n,\r 제외 제어문자

def extract_exe():
    b = open(EXE, "rb").read()
    assert b[:4] == b"NSO0", "NSO0 아님"
    ro_fo, ro_mo, ro_sz = struct.unpack_from("<III", b, 0x20)  # .rodata
    ro = b[ro_fo:ro_fo+ro_sz]
    out = defaultdict(list)   # jp -> [(abs_offset, byte_len)]
    pos = 0
    for tok in ro.split(b"\x00"):
        L = len(tok)
        if L >= 2 and KANA.search(tok):
            try: s = tok.decode("utf-8")
            except Exception: s = None
            if s and JP.search(s) and not CTRL.search(s):
                out[s].append((ro_fo + pos, L))
        pos += L + 1
    return out

def main():
    exe = extract_exe()
    print("실행파일 고유 일본어: %d, 등장 %d" % (len(exe), sum(len(v) for v in exe.values())))
    doc = json.load(open(JSONF, encoding="utf-8"))
    by_jp = {s["jp"]: s for s in doc["strings"]}
    added_new = 0; added_occ = 0
    for jp, locs in exe.items():
        occ = [{"file": "main", "method": "exe", "offset": o, "len": l} for o, l in locs]
        if jp in by_jp:
            s = by_jp[jp]
            s["occurrences"].extend(occ)
            s["count"] = len(s["occurrences"])
            added_occ += len(occ)
        else:
            doc["strings"].append({
                "id": 0, "category": "exe", "jp": jp, "ko": "",
                "count": len(occ), "occurrences": occ,
            })
            by_jp[jp] = doc["strings"][-1]; added_new += 1; added_occ += len(occ)
    # 재정렬(카테고리 text>name>other>exe → 등장수) + id 재부여
    rank = {"text": 0, "name": 1, "other": 2, "exe": 3}
    doc["strings"].sort(key=lambda s: (rank.get(s["category"], 9), -s["count"], s["jp"]))
    for i, s in enumerate(doc["strings"], 1): s["id"] = i
    from collections import Counter
    catc = Counter(s["category"] for s in doc["strings"])
    doc["meta"]["unique_strings"] = len(doc["strings"])
    doc["meta"]["total_occurrences"] = sum(s["count"] for s in doc["strings"])
    doc["meta"]["by_category"] = dict(catc)
    doc["meta"]["exe_source"] = EXE
    json.dump(doc, open(JSONF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("신규 exe 문자열 %d, 기존문자열에 추가된 exe 등장 %d" % (added_new, added_occ))
    print("병합 후 카테고리:", dict(catc))
    print("총 고유:", len(doc["strings"]), " JSON %.1f MB" % (os.path.getsize(JSONF)/1e6))

if __name__ == "__main__":
    main()
