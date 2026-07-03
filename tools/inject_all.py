# -*- coding: utf-8 -*-
"""번역 주입 오케스트레이터: 번역_일본어.json(ko 채움) → 패치된 CHK + main
- string 방식(CHK STRING 청크): 문자열 교체 후 청크 재구성
- scan 방식(CHK 0x00-split): 오프셋 제자리 치환(길이제약)
- exe 방식(main .rodata): 오프셋 제자리 치환(길이제약)
- 한국어→한자코드 인코딩(CHK=메인 wReplace, exe=tsv)
출력: inject_out/  (CHK는 REPACK_AUTO repack_in/ 으로, main은 elf2nso 재빌드)
사용법: python inject_all.py [번역_일본어.json]
"""
import os, sys, json, struct
from collections import defaultdict
import inject_lib as L

JSONF   = sys.argv[1] if len(sys.argv) > 1 else "번역_일본어.json"
RES     = "RES_추출원본"
EXE_SRC = os.path.join("!exefs-작업", "main-원본")
CHK_OUT = "repack_in"      # 패치 CHK → REPACK_AUTO 입력 폴더(바로 재패킹 가능)
EXE_OUT = "inject_out"     # 패치 main → elf2nso 재빌드용
ENC_CHK = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv"))  # 통일: tsv(가→亜) — 2026-07-03 폰트 단일화
ENC_EXE = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv")) # exe/ADD 블록(가→亜)

def main():
    doc = json.load(open(JSONF, encoding="utf-8"))
    chk_string = defaultdict(dict)        # file -> {index: ko_bytes}
    chk_scan   = defaultdict(list)        # file -> [(offset, len, ko_bytes)]
    exe_patch  = []                       # [(offset, len, ko_bytes)]
    miss_glyph = set(); trunc = []
    n_tr = 0
    for s in doc["strings"]:
        ko = s.get("ko", "").strip()
        if not ko: continue
        n_tr += 1
        for occ in s["occurrences"]:
            mth = occ["method"]
            enc = ENC_EXE if mth == "exe" else ENC_CHK
            miss_glyph.update(enc.covers(ko))
            kob = enc.encode(ko)
            if mth == "string":
                chk_string[occ["file"]][occ["index"]] = kob
            elif mth == "scan":
                chk_scan[occ["file"]].append((occ["offset"], occ["len"], kob))
            elif mth == "exe":
                exe_patch.append((occ["offset"], occ["len"], kob))
    os.makedirs(CHK_OUT, exist_ok=True); os.makedirs(EXE_OUT, exist_ok=True)
    files_done = 0
    # --- CHK: string 방식(청크 재구성) ---
    for fn, repl in chk_string.items():
        src = os.path.join(RES, fn)
        if not os.path.isfile(src):
            print("  [없음]", fn); continue
        b = open(src, "rb").read()
        strs = L.parse_string_list(b)
        if strs is None:
            print("  [STRING없음]", fn); continue
        new = list(strs)
        for idx, kob in repl.items():
            if 0 <= idx < len(new): new[idx] = kob
        out = L.rebuild_string_chk(b, new)
        open(os.path.join(CHK_OUT, fn), "wb").write(out)
        files_done += 1
    # --- CHK: scan 방식(오프셋 치환) ---
    for fn, patches in chk_scan.items():
        if fn in chk_string: continue   # 같은 파일이 양쪽이면 string 우선(보통 없음)
        src = os.path.join(RES, fn)
        if not os.path.isfile(src): print("  [없음]", fn); continue
        buf = bytearray(open(src, "rb").read())
        for off, ln, kob in patches:
            if L.patch_at_offset(buf, off, ln, kob): trunc.append((fn, off, len(kob), ln))
        open(os.path.join(CHK_OUT, fn), "wb").write(buf)
        files_done += 1
    # --- exe: main .rodata 오프셋 치환 ---
    if exe_patch:
        buf = bytearray(open(EXE_SRC, "rb").read())
        for off, ln, kob in exe_patch:
            if L.patch_at_offset(buf, off, ln, kob): trunc.append(("main", off, len(kob), ln))
        open(os.path.join(EXE_OUT, "main"), "wb").write(buf)
        files_done += 1
    print("="*60)
    print("번역된 문자열 %d개 → 패치 파일 %d개 (CHK→%s/, main→%s/)" % (n_tr, files_done, CHK_OUT, EXE_OUT))
    print("  CHK(string 재구성) %d, CHK(scan 치환) %d, exe 패치 %d occ" %
          (len(chk_string), len(chk_scan), len(exe_patch)))
    if trunc:  print("  [!] 길이초과로 잘림 %d건 (원본 바이트 한도 초과)" % len(trunc))
    if miss_glyph: print("  [!] 폰트 미지원 한글 음절 %d종: %s" % (len(miss_glyph), "".join(sorted(miss_glyph))[:40]))
    print("다음: (CHK) python REPACK_AUTO.py  →  repack_out/RES00.RDB 등")
    print("      main 은 !exefs-작업에서 elf2nso 로 재빌드")
    print("="*60)

if __name__ == "__main__":
    main()
