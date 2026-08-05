# -*- coding: utf-8 -*-
"""main-safe7 → main-safe8:
 1) 잔여 일본어 꼬리조각 377개 번역 주입(_frag_translations.json; 빈번역=NUL 소거)
 2) .rodata 내 raw 한글(=tsv 미지원 잔존, 큥/챳 등) → 자모 폴백 음절의 tsv 한자로 치환(등길이)
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import inject_lib as L

ENC = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv"))
TSV = ENC.m

CHO = 19
JUNG_ALT = {2:0, 6:4, 12:8, 17:13, 3:1, 7:5, 9:8, 10:0, 11:1, 14:13, 15:4, 16:5, 19:18}
def fallback_syl(c):
    v = ord(c) - 0xAC00
    cho, jung, jong = v // 588, (v % 588) // 28, v % 28
    cands = []
    if jong: cands.append((cho, jung, 0))
    j2 = JUNG_ALT.get(jung)
    if j2 is not None:
        cands.append((cho, j2, jong)); cands.append((cho, j2, 0))
    for ch, ju, jo in cands:
        s = chr(0xAC00 + ch*588 + ju*28 + jo)
        if s in TSV: return s
    return None

buf = bytearray(open('inject_out/main-safe7', 'rb').read())
LO, HI = 0x3d00000, 0x5600000

# ---- 1) 조각 주입 ----
cand = json.load(open('_exe_frag_cand.json', encoding='utf-8'))
tr = {r['i']: r['ko'] for r in json.load(open('_frag_translations.json', encoding='utf-8'))}
def cur_len(off):
    e = buf.find(b'\x00', off)
    return e - off if e >= 0 else 0
p = emptied = trunc = 0
for i, item in enumerate(cand):
    ko = (tr.get(i) or '').strip()
    kob = ENC.encode(ko) if ko else b''
    for off in item['offs']:
        ol = cur_len(off)
        if ol == 0: continue
        if L.patch_at_offset(buf, off, ol, kob): trunc += 1
        p += 1
    if not ko: emptied += 1
print(f"[조각] {p} occ 주입(빈소거 {emptied}건, 절단 {trunc})")

# ---- 2) raw 한글 폴백 ----
n_sub = 0; miss = {}
i = LO
while i < HI - 2:
    b0 = buf[i]
    if 0xEA <= b0 <= 0xED:               # 한글 UTF-8 선두(U+AC00-D7A3 ⊂ EA B0 80 ~ ED 9E A3)
        try:
            c = bytes(buf[i:i+3]).decode('utf-8')
        except UnicodeDecodeError:
            i += 1; continue
        if len(c) == 1 and '가' <= c <= '힣':
            if c in TSV:
                rep = TSV[c]                     # 지원 음절이 raw로 남은 경우 → 직접 인코딩
            else:
                f = fallback_syl(c)
                rep = TSV.get(f) if f else None
                if rep is None: rep = '・'
            buf[i:i+3] = rep.encode('utf-8')
            n_sub += 1
            miss[c] = miss.get(c, 0) + 1
            i += 3; continue
    i += 1
print(f"[폴백] raw 한글 치환 {n_sub}건: {dict(sorted(miss.items(), key=lambda x:-x[1])[:10])}")

open('inject_out/main-safe8', 'wb').write(buf)
print(f"저장 inject_out/main-safe8 ({len(buf)}B)")
# 무결성: 변경범위
s7 = open('inject_out/main-safe7', 'rb').read()
diff = [k for k in range(len(buf)) if buf[k] != s7[k]]
if diff:
    print(f"safe7→8 변경 {len(diff)}B, 범위 0x{min(diff):x}~0x{max(diff):x}, 전부 문자열영역 {all(LO<=k<HI for k in diff)}")
