# -*- coding: utf-8 -*-
"""씬 재번역 병합·검증: _scene_tr_out/b*.json → _scene_tr_merged.json / _scene_tr_bad.json
검증: %지정자 일치, <태그> 일치, \n 개수 일치, tsv 인코딩 후 바이트예산, 가나 잔존, 비표준 음절"""
import sys, os, json, re, glob
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
print('번역대상', len(meta))

SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|%%')
TAG = re.compile(r'<[^<>\n]{1,24}>')
KANA = re.compile(r'[぀-ゟ゠-ヿ]')
ALLOW_KANA = set('ー・～')

merged = {}
bad = {}
dup = 0
for fp in sorted(glob.glob('_scene_tr_out/b*.json')):
    try: arr = json.load(open(fp, encoding='utf-8'))
    except Exception as e:
        print('  [파스실패]', fp, e); continue
    if isinstance(arr, dict): arr = arr.get('results', [])
    for r in arr:
        if not isinstance(r, dict) or 'i' not in r: continue
        i = r['i']; ko = (r.get('ko') or '').strip('\x00')
        if i not in meta: continue
        if i in merged or i in bad: dup += 1; continue
        m = meta[i]; jp = m['jp']
        why = []
        if not ko:
            why.append('empty')
        else:
            if sorted(SPEC.findall(jp)) != sorted(SPEC.findall(ko)): why.append('spec')
            if sorted(TAG.findall(jp)) != sorted(TAG.findall(ko)): why.append('tag')
            if jp.count('\n') != ko.count('\n'): why.append('nl')
            kana = [c for c in ko if KANA.match(c) and c not in ALLOW_KANA]
            if kana: why.append('kana')
            badch = [c for c in ko if '가' <= c <= '힣' and c not in TSV]
            if badch: why.append('syl:' + ''.join(badch[:4]))
            if len(enc(ko)) > m['maxb']: why.append(f"len{len(enc(ko))}>{m['maxb']}")
            if any(ord(c) < 0x20 and c != '\n' for c in ko): why.append('ctrl')
        if why: bad[i] = {'jp': jp, 'ko': ko, 'why': why, 'maxb': m['maxb']}
        else: merged[i] = ko
missing = [i for i in meta if i not in merged and i not in bad]
print(f"병합 {len(merged):,} / 불량 {len(bad):,} / 미수신 {len(missing):,} / 중복 {dup}")
import collections
wc = collections.Counter()
for v in bad.values():
    for w in v['why']: wc[w.split(':')[0].rstrip('0123456789>')] += 1
print('불량 사유:', dict(wc.most_common(10)))
json.dump(merged, open('_scene_tr_merged.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(bad, open('_scene_tr_bad.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(missing, open('_scene_tr_missing.json', 'w'))
