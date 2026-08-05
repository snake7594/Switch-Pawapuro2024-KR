# -*- coding: utf-8 -*-
"""_sweep_unknown.json + _sweep_translations.json({jp→ko}) → _sweep_patches.json(plan 형식).
tsv 인코딩, ·→・ 등 문자수정, 예산 초과시 공백제거→클린절단."""
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
def charfix(s): return s.replace('·', '・').replace('—', 'ー')

unknown = json.load(open('_sweep_unknown.json', encoding='utf-8'))
tr = json.load(open('_sweep_translations.json', encoding='utf-8'))
plans = {}
n_p = n_skip = n_trunc = 0
for jp, info in unknown.items():
    ko = (tr.get(jp) or '').strip()
    if not ko or ko == jp:
        n_skip += 1; continue
    ko = charfix(ko)
    for (name, off, budget) in info['occ']:
        nb = enc(ko)
        if len(nb) > budget:
            nb2 = enc(ko.replace(' ', ''))
            nb = nb2 if len(nb2) <= budget else nb[:budget]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
            n_trunc += 1
        region = budget + 1   # budget = region-1 (NUL 1개 보장분)
        plans.setdefault(name, {'aligned': True, 'patches': []})['patches'].append([off, region, nb.hex()])
        n_p += 1
json.dump(plans, open('_sweep_patches.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"패치 {n_p} occ ({len(plans)} 슬롯), 스킵 {n_skip}, 절단 {n_trunc} → _sweep_patches.json")
