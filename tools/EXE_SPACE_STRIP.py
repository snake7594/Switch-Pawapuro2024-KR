# -*- coding: utf-8 -*-
"""exe 메뉴 라벨 공백 제거: 주입 diff 세그 중 라벨성 문자열 공백 제거. 씬 대사(foff)는 제외.
입력: inject_out/main-safe27 (씬 수리 주입본) → main-safe26"""
import sys, os, json, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

SRC = 'inject_out/main-safe27'
DST = 'inject_out/main-safe28'

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
TSVR = {v: k for k, v in TSV.items()}
def dec_ko(s): return ''.join(TSVR.get(c, c) for c in s)
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

# 씬 대사 foff 제외 집합
inp = json.load(open('_scene_tr_input.json', encoding='utf-8'))
scene_foffs = set()
for sc in inp:
    for l in sc['lines']:
        if l['t'] == 'tr': scene_foffs.add(l['foff'])
print('씬 대사 제외 foff', len(scene_foffs))

JP_PUNCT = set('。！？…、,.!?~～')
KO_PUNCT = set('.,!?…~～、。')
SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|<[^<>\n]{1,24}>')
def label_fixable(jp, ko):
    if ' ' in jp or '　' in jp: return None
    if len(jp) > 16 or not jp: return None
    if any(c in JP_PUNCT for c in jp): return None
    if '\n' in jp or '\n' in ko: return None
    if SPEC.search(jp) or SPEC.search(ko): return None
    if ' ' not in ko and '　' not in ko: return None
    if any(c in KO_PUNCT for c in ko): return None
    if not any('가' <= c <= '힣' for c in ko): return None
    return ko.replace(' ', '').replace('　', '')

ob = open('main', 'rb').read()
buf = bytearray(open(SRC, 'rb').read())
DYN = (0x2aafb79, 0x3d2551d)
a = np.frombuffer(bytes(buf), dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
diff = np.nonzero(a != b)[0]
sel = diff[diff >= DYN[1]]
stats = dict(strip=0)
samples = []
# 세그먼트 시작만 추출(중복 제거)
snap = bytes(buf)
starts = set()
for x in sel.tolist():
    st = x
    while st > DYN[1] and ob[st-1] != 0: st -= 1
    starts.add(st)
print(f"검사 세그먼트 {len(starts)}", flush=True)
for st in starts:
    if st in scene_foffs: continue
    oe = ob.find(b'\x00', st)
    if oe < 0: continue
    ce = snap.find(b'\x00', st)
    if ce < 0 or ce == st: continue
    try:
        jp = ob[st:oe].decode('utf-8')
        cur = bytes(buf[st:ce]).decode('utf-8')
    except UnicodeDecodeError: continue
    ko = dec_ko(cur)
    new = label_fixable(jp, ko)
    if new is None or new == ko: continue
    nb = enc(new)
    T = 0; k2 = oe
    while k2 < len(ob) and ob[k2] == 0: T += 1; k2 += 1
    region_end = oe + T
    if st + len(nb) >= region_end: continue
    buf[st:st+len(nb)] = nb
    buf[st+len(nb):region_end] = b'\x00' * (region_end - st - len(nb))
    stats['strip'] += 1
    if len(samples) < 14: samples.append(f'{ko!r}→{new!r}')
c = np.frombuffer(bytes(buf), dtype=np.uint8)
s0 = np.frombuffer(open(SRC, 'rb').read(), dtype=np.uint8)
assert (c[:DYN[1]] == s0[:DYN[1]]).all(), "금지영역 변경!"
open(DST, 'wb').write(bytes(buf))
print(f"완료: {stats} → {DST}")
print(*samples, sep='\n')
