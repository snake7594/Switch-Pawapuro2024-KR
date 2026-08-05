# -*- coding: utf-8 -*-
"""실황2024 전체 일본어 텍스트 추출 → JSON (번역용)
소스: RES_추출원본/*.CHK (게임 전체 언팩본)
- CHK 'STRING' 청크: 구조화 추출 (file, index) — 재주입 정밀
- 그 외 JP 보유 CHK: 0x00-split UTF-8 (file, offset, byte_len) — 이름표/기타
- 고유 일본어로 그룹화, ko 빈칸, 등장위치 목록 포함
사용법: python extract_jp_text.py [소스폴더]
"""
import os, sys, glob, json, struct, re
from multiprocessing import Pool, cpu_count
from collections import defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "RES_추출원본"
OUT = "번역_일본어.json"

# 일본어 문자(번역대상): 히라가나/가타카나/한자/CJK기호/반각가타카나
JP = re.compile(
    "[぀-ゟ゠-ヿㇰ-ㇿ㐀-䶿一-鿿"
    "豈-﫿ｦ-ﾝ々〆〇〻]"
)
# 원시 바이트 빠른 사전필터(UTF-8 일본어 3바이트 후보)
JP_RAW = re.compile(rb"[\xe3-\xe9][\x80-\xbf][\x80-\xbf]")
# 가나(히라가나 U+3040-309F=E3 81-82.., 가타카나 U+30A0-30FF=E3 82-83) 존재 = 일본어 파일
# + 반각 가타카나 U+FF66-FF9D = EF BD A6.. / EF BE ..
KANA_RAW = re.compile(rb"\xe3[\x81-\x83]|\xef\xbd[\xa6-\xbf]|\xef\xbe[\x80-\x9d]")

def u32(b, o): return struct.unpack_from("<I", b, o)[0]

def parse_string_chunks(b):
    """모든 'STRING' 청크에서 (index, text) 추출. text는 NUL종료 UTF-8."""
    out = []  # (global_index, text)
    start = 0
    gidx = 0
    while True:
        si = b.find(b"STRING", start)
        if si < 0: break
        start = si + 6
        base = si + 0x10
        if base + 4 > len(b): continue
        p0 = u32(b, base)
        if p0 < 4 or p0 % 4 or p0 > 0x200000: continue
        N = p0 // 4
        if base + 4*N > len(b): continue
        # 포인터가 단조 비감소인지 가볍게 검증
        prev = -1; ok = True; ptrs = []
        for k in range(N):
            off = u32(b, base + 4*k)
            if off < prev or base + off > len(b): ok = False; break
            prev = off; ptrs.append(off)
        if not ok or not ptrs: continue
        for off in ptrs:
            s = base + off
            e = b.find(b"\x00", s)
            if e < 0: e = len(b)
            try: txt = b[s:e].decode("utf-8")
            except Exception: txt = None
            out.append((gidx, txt)); gidx += 1
    return out

def scan_nul(b):
    """0x00-split UTF-8 토큰 → (offset, byte_len, text)."""
    out = []
    pos = 0
    for tok in b.split(b"\x00"):
        ln = len(tok)
        if ln >= 2 and JP_RAW.search(tok):
            try: txt = tok.decode("utf-8")
            except Exception: txt = None
            if txt and JP.search(txt):
                out.append((pos, ln, txt))
        pos += ln + 1
    return out

def category(fname, method):
    n = fname.upper()
    if method == "string": return "text"
    if n.startswith("SEN_") or "NAME" in n or "MEIKAN" in n or "MANNAME" in n:
        return "name"
    return "other"

def process(path):
    fn = os.path.basename(path)
    try:
        b = open(path, "rb").read()
    except Exception:
        return []
    # 가나가 전혀 없는 파일(중국어 HSIMSCH 등 타언어/비텍스트)은 제외
    if not KANA_RAW.search(b):
        return []
    entries = []
    # 1) STRING 청크(구조화)
    for idx, txt in parse_string_chunks(b):
        if txt and JP.search(txt):
            entries.append((txt, fn, {"index": idx}, "string"))
    # 2) STRING에서 못 얻었으면 0x00-split
    if not entries:
        for off, ln, txt in scan_nul(b):
            entries.append((txt, fn, {"offset": off, "len": ln}, "scan"))
    return entries

def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.CHK")))
    print("스캔 대상 CHK: %d개 (소스 %s)" % (len(files), SRC))
    groups = defaultdict(lambda: {"occ": [], "methods": set(), "cats": set()})
    nproc = max(1, min(cpu_count()-1, 12))
    done = 0
    with Pool(nproc) as pool:
        for entries in pool.imap_unordered(process, files, chunksize=16):
            for txt, fn, loc, method in entries:
                g = groups[txt]
                g["occ"].append(dict(file=fn, method=method, **loc))
                g["methods"].add(method)
                g["cats"].add(category(fn, method))
            done += 1
            if done % 2000 == 0:
                print("  ...%d/%d CHK, 고유문자열 %d" % (done, len(files), len(groups)))
    # 정렬: 카테고리(text>name>other) → 등장수 내림차순
    catrank = {"text": 0, "name": 1, "other": 2}
    def pick_cat(cats):
        return sorted(cats, key=lambda c: catrank.get(c, 9))[0]
    items = []
    for txt, g in groups.items():
        items.append((pick_cat(g["cats"]), -len(g["occ"]), txt, g))
    items.sort(key=lambda x: (catrank.get(x[0], 9), x[1], x[2]))
    strings = []
    for i, (cat, negc, txt, g) in enumerate(items, 1):
        strings.append({
            "id": i, "category": cat, "jp": txt, "ko": "",
            "count": len(g["occ"]), "occurrences": g["occ"],
        })
    from collections import Counter
    catc = Counter(s["category"] for s in strings)
    occ_total = sum(s["count"] for s in strings)
    out = {
        "meta": {
            "source": SRC, "chk_scanned": len(files),
            "unique_strings": len(strings), "total_occurrences": occ_total,
            "by_category": dict(catc),
        },
        "strings": strings,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("="*60)
    print("완료: 고유 일본어 %d개, 등장 총 %d회" % (len(strings), occ_total))
    print("카테고리:", dict(catc))
    print("저장:", OUT, "(%.1f MB)" % (os.path.getsize(OUT)/1e6))
    print("="*60)

if __name__ == "__main__":
    main()
