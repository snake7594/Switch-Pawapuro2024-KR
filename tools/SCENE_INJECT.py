# -*- coding: utf-8 -*-
"""씬 재번역 주입: main-safe23 → main-safe24.
- _scene_tr_merged.json(+_scene_tr_fix.json 있으면 우선)을 foff 제자리 주입(tsv 인코딩, region=세그+후행NUL)
- 금지영역(pre-rodata / DYNAMIC[0x2aafb79,0x3d2551d]) 침범 assert"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

inp = json.load(open('_scene_tr_input.json', encoding='utf-8'))
meta = {}
for sc in inp:
    for l in sc['lines']:
        if l['t'] == 'tr': meta[l['i']] = l
tr = json.load(open('_scene_tr_merged.json', encoding='utf-8'))
if os.path.isfile('_scene_tr_fix.json'):
    fx = json.load(open('_scene_tr_fix.json', encoding='utf-8'))
    tr.update(fx)
    print('fix 반영', len(fx))
tr = {int(k): v for k, v in tr.items()}
print('주입 후보', len(tr))

import os as _os
BASE = _os.environ.get('SCENE_BASE', 'inject_out/main-safe23')
DSTP = _os.environ.get('SCENE_DST', 'inject_out/main-safe24')
ob = open('main', 'rb').read()
buf = bytearray(open(BASE, 'rb').read())
DYN = (0x2aafb79, 0x3d2551d)
stats = dict(inj=0, skip_fit=0, same=0)
for i, ko in tr.items():
    m = meta.get(i)
    if not m: continue
    fo = m['foff']
    assert fo > DYN[1], f"금지영역 주입 시도 {hex(fo)}"
    jp_b = m['jp'].encode('utf-8')
    # 원본 세그 확인
    if ob[fo:fo+len(jp_b)] != jp_b: continue
    # region = 세그 + 후행 NUL
    e = fo + len(jp_b)
    T = 0
    while e + T < len(ob) and ob[e + T] == 0: T += 1
    region = len(jp_b) + T
    nb = enc(ko)
    if len(nb) > region - 1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
        stats['skip_fit'] += 1
    if bytes(buf[fo:fo+len(nb)]) == nb and all(c == 0 for c in buf[fo+len(nb):fo+region]):
        stats['same'] += 1; continue
    buf[fo:fo+len(nb)] = nb
    buf[fo+len(nb):fo+region] = b'\x00' * (region - len(nb))
    stats['inj'] += 1
# 금지영역 불변 assert
import numpy as np
a = np.frombuffer(bytes(buf), dtype=np.uint8)
c = np.frombuffer(open(BASE, 'rb').read(), dtype=np.uint8)
assert (a[:DYN[1]] == c[:DYN[1]]).all(), "금지영역 변경!"
open(DSTP, 'wb').write(bytes(buf))
print(f"완료: {stats} → {DSTP}")
