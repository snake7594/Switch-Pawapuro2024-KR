# -*- coding: utf-8 -*-
"""exe 대본 재구성: RELA 재배치의 연속 슬롯 런 = 시나리오 대본.
- RELA(VA 0x2ab0058, cnt 0xc36e2) 파싱 → r_offset 정렬 → 스트라이드(8/16/24/32) 런 검출
- 런 내 각 addend → .rodata 문자열. 가나 대사 비율 높은 런 = 씬(대본)
- 출력: _scenes.json [{run_id, slot_va0, stride, lines:[{i, va, foff, budget, jp}]}] + 통계"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

b = open('main', 'rb').read()
F, M = 0x2aafb21, 0x2ab0000
ROD_END = F + 0x2fb8e68
RELA_F = 0x2ab0058 - M + F
RELA_CNT = 0xc36e2
rela = np.frombuffer(b[RELA_F:RELA_F+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
mask = rela[:, 1] == 0x403
offs = rela[mask, 0].astype(np.int64)
adds = rela[mask, 2].astype(np.int64)
order = np.argsort(offs, kind='stable')
offs, adds = offs[order], adds[order]
print(f"RELATIVE 재배치 {len(offs):,}")

# addend가 .rodata 문자열 범위인 것만 (문자열 포인터 후보)
va_lo, va_hi = M, M + (ROD_END - F)
is_str = (adds >= va_lo) & (adds < va_hi)

def seg_at(fo):
    e = b.find(b'\x00', fo)
    if e < 0 or e == fo: return None
    raw = b[fo:e]
    try: return raw.decode('utf-8')
    except UnicodeDecodeError: return None

def kana_or_cjk(s):
    return any('぀' <= c <= 'ヿ' or '一' <= c <= '鿿' for c in s)

# 런 검출: 같은 스트라이드로 이어지는 연속 슬롯
runs = []
i = 0
N = len(offs)
while i < N - 1:
    if not is_str[i]: i += 1; continue
    stride = offs[i+1] - offs[i]
    if stride not in (8, 16, 24, 32) or not is_str[i+1]:
        i += 1; continue
    j = i + 1
    while j + 1 < N and offs[j+1] - offs[j] == stride and is_str[j+1]:
        j += 1
    if j - i + 1 >= 3:
        runs.append((int(offs[i]), int(stride), i, j))
    i = j + 1
print(f"런(>=3) {len(runs):,}")

scenes = []
tot_lines = 0
for rid, (va0, stride, i0, i1) in enumerate(runs):
    lines = []
    n_jp = 0
    for k in range(i0, i1 + 1):
        fo = int(adds[k]) - M + F
        s = seg_at(fo)
        if s is None:
            lines.append(None); continue
        # 예산: 원본 세그 + 후행 NUL 런
        e = fo + len(s.encode('utf-8'))
        T = 0
        while e + T < len(b) and b[e + T] == 0: T += 1
        budget = (e - fo) + (T - 1 if T > 0 else 0)
        jpish = kana_or_cjk(s)
        if jpish: n_jp += 1
        lines.append({'va': int(adds[k]), 'foff': fo, 'budget': budget, 'jp': s, 'jpish': jpish})
    n_valid = sum(1 for x in lines if x)
    if n_valid == 0: continue
    ratio = n_jp / n_valid
    if n_jp >= 3 and ratio >= 0.5:
        scenes.append({'run_id': rid, 'slot_va0': va0, 'stride': stride, 'lines': lines})
        tot_lines += n_jp
print(f"대사 씬 런 {len(scenes):,}, 일본어 라인 총 {tot_lines:,}")
ln = [sum(1 for x in sc['lines'] if x and x['jpish']) for sc in scenes]
import collections
h = collections.Counter()
for x in ln:
    h['3-5' if x <= 5 else '6-20' if x <= 20 else '21-100' if x <= 100 else '100+'] += 1
print('씬 크기 분포:', dict(h))
json.dump(scenes, open('_scenes.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('saved _scenes.json')
# 표본 출력
for sc in scenes[:2]:
    print('---- scene', sc['run_id'], 'stride', sc['stride'], hex(sc['slot_va0']))
    for x in sc['lines'][:8]:
        if x: print('   ', repr(x['jp'][:48]))
