# -*- coding: utf-8 -*-
"""'그럴듯한 일본어' 판정 v2 — 유니코드 블록 기반(♥◆Ω№·PUA 글리프 등 실문자열 허용).
바이너리 오탐 기준: 허용블록 밖 문자 / 제어문자 / 가나0이면서 미실증 한자."""
import json, os
_here = os.path.dirname(os.path.abspath(__file__))
doc = json.load(open(os.path.join(_here, '번역_일본어.json'), encoding='utf-8'))
def _has_kana(s): return any('぀' <= c <= 'ヿ' for c in s)
REAL_KANJI = set()
for _s in doc['strings']:
    jp = _s['jp']
    if _has_kana(jp) and not any(ord(c) < 0x20 for c in jp):
        for c in jp:
            if '一' <= c <= '鿿': REAL_KANJI.add(c)

def _blk_ok(o):
    return (0x20 <= o < 0x7f or o in (0x0a, 0x09)
            or 0x00a0 <= o <= 0x00ff      # Latin-1 기호
            or 0x0370 <= o <= 0x03ff      # 그리스(Ω)
            or 0x2000 <= o <= 0x27bf      # 일반구두점~딩벳(…※→♥◆①)
            or 0x2e80 <= o <= 0x2fdf      # 부수
            or 0x3000 <= o <= 0x30ff      # CJK구두점+가나
            or 0x3190 <= o <= 0x319f
            or 0x31f0 <= o <= 0x31ff
            or 0x3200 <= o <= 0x33ff      # 괄호문자·단위(㎞ ㌍)
            or 0x3400 <= o <= 0x9fff      # 한자(확A 포함)
            or 0xf900 <= o <= 0xfaff      # 호환한자(﨑 등 인명 가이지)
            or 0xfe30 <= o <= 0xfe4f
            or 0xff00 <= o <= 0xffef      # 전각/반각
            or 0xe000 <= o <= 0xf8ff      # PUA(커스텀 글리프)
            or 0x1f000 <= o <= 0x1faff
            or 0xf0000 <= o <= 0x10fffd)  # PUA 15/16면(글리프 플레이스홀더)

def plausible_jp(s, lenient=False):
    """lenient=True: exe .rodata용(진짜 문자열 풀) — 가나 없는 한자열에 ASCII 혼용 허용('%d億' 등)."""
    if not s or len(s) < 2: return False
    for c in s:
        o = ord(c)
        if o < 0x20 and c not in '\n\t': return False
        if 0x7f <= o < 0xa0: return False
        if not _blk_ok(o): return False
    nk = sum(1 for c in s if '぀' <= c <= 'ヿ')
    if nk: return True
    # 가나 없음: 한자 전부 실증(REAL_KANJI ∪ 호환한자)이어야
    kj = [c for c in s if 0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff]
    if not kj: return False
    for c in kj:
        if not (c in REAL_KANJI or 0xf900 <= ord(c) <= 0xfaff): return False
    if len(kj) >= 2: return True
    # 한자 1자: 나머지가 전각/CJK구두점/기호/PUA(+lenient시 ASCII)뿐이면 허용(예: 何？, %d億)
    for c in s:
        o = ord(c)
        if c in kj: continue
        if lenient and 0x20 <= o < 0x7f: continue
        if not (0xff00 <= o <= 0xffef or 0x3000 <= o <= 0x303f or 0x2000 <= o <= 0x27bf
                or 0xe000 <= o <= 0xf8ff or 0xf0000 <= o <= 0x10fffd): return False
    return True
