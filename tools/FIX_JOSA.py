# -*- coding: utf-8 -*-
"""조사 병기 최소 수정(빠른 바이트검색): '이(가)'·'을(를)' 등을 앞 글자 받침으로 확정.
- 앞 글자가 완성형 한글일 때만 확정. 변수(%s)·기호 뒤는 유지.
- 베이스: main-mylife-exp (v1.2) → main-b. 병기 있는 세그만 제자리 재기록."""
import sys, os, re, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv(); TSVR = {v: k for k, v in TSV.items()}
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def dec(seg):
    try: return ''.join(TSVR.get(c, c) for c in seg.decode('utf-8'))
    except UnicodeDecodeError: return None
def has_batchim(ch):
    if not ('가' <= ch <= '힣'): return None
    return (ord(ch) - 0xAC00) % 28 != 0

PAIRS = [('이(가)','이','가'),('가(이)','이','가'),('을(를)','을','를'),('를(을)','을','를'),
         ('은(는)','은','는'),('는(은)','은','는'),('과(와)','과','와'),('와(과)','과','와'),
         ('이／가','이','가'),('을／를','을','를'),('은／는','은','는'),('과／와','과','와'),('와／과','과','와')]
PAT = re.compile('(' + '|'.join(re.escape(p[0]) for p in PAIRS) + ')')
LOOK = {p[0]: (p[1], p[2]) for p in PAIRS}

def resolve(ko):
    out = []; i = 0; changed = False
    for m in PAT.finditer(ko):
        s, e = m.span(); tok = m.group(1)
        prev = ko[s-1] if s > 0 else ''
        bat = has_batchim(prev)
        chosen = None
        if bat is not None and tok in LOOK:
            b1, b0 = LOOK[tok]; chosen = b1 if bat else b0
        out.append(ko[i:s]); out.append(chosen if chosen else tok); i = e
        if chosen: changed = True
    out.append(ko[i:])
    return ''.join(out), changed

BASE = 'inject_out/main-mylife-exp'; OUT = 'inject_out/main-b'
buf = bytearray(open(BASE, 'rb').read())
def u32(o): return struct.unpack_from('<I', bytes(buf), o)[0]
DYN_HI = 0x3d2551d; DATA_FO = u32(0x30)
snap = bytes(buf)
# 각 병기 패턴 바이트 검색 → 세그 시작 수집
seg_starts = set()
for pat, _, _ in PAIRS:
    pb = enc(pat); start = DYN_HI
    while True:
        p = snap.find(pb, start)
        if p < 0 or p >= DATA_FO: break
        st = p
        while st > DYN_HI and snap[st-1] != 0: st -= 1
        seg_starts.add(st); start = p + 1
print(f"병기 세그 {len(seg_starts)}")
stats = dict(fix=0, kept=0)
for st in seg_starts:
    e = snap.find(b'\x00', st)
    if e < 0: continue
    ko = dec(snap[st:e])
    if ko is None: continue
    new, changed = resolve(ko)
    if not changed: stats['kept'] += 1; continue
    nb = enc(new)
    T = 0; k = e
    while k < len(buf) and buf[k] == 0: T += 1; k += 1
    region = (e - st) + T
    if len(nb) <= region - 1:
        buf[st:st+len(nb)] = nb
        buf[st+len(nb):st+region] = b'\x00' * (region - len(nb))
        stats['fix'] += 1
    else: stats['kept'] += 1
import numpy as np, hashlib
c = np.frombuffer(bytes(buf), dtype=np.uint8); base = np.frombuffer(snap, dtype=np.uint8)
assert (c[:DYN_HI] == base[:DYN_HI]).all(), "동적영역 변경!"
open(OUT, 'wb').write(bytes(buf))
print(f"확정수정 {stats['fix']}, 유지 {stats['kept']} → {OUT} md5 {hashlib.md5(bytes(buf)).hexdigest()}")
