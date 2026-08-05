# -*- coding: utf-8 -*-
"""루비/정렬 수리 출력(_repair_out/*.json) 검증·병합 → _scene_tr_fix.json 갱신.
검증: spec/tag/nl/kana/음절/바이트 통과분만 반영(불량은 기존 유지)."""
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
SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|%%')
TAG = re.compile(r'<[^<>\n]{1,24}>')
KANA = re.compile(r'[぀-ゟ゠-ヿ]')
ALLOW = set('ー・～')
def bad(jp, ko, maxb):
    if not ko: return 'empty'
    if sorted(SPEC.findall(jp)) != sorted(SPEC.findall(ko)): return 'spec'
    if sorted(TAG.findall(jp)) != sorted(TAG.findall(ko)): return 'tag'
    if jp.count('\n') != ko.count('\n'): return 'nl'
    if any(KANA.match(c) and c not in ALLOW for c in ko): return 'kana'
    if any('가' <= c <= '힣' and c not in TSV for c in ko): return 'syl'
    if len(enc(ko)) > maxb: return 'len'
    if any(ord(c) < 0x20 and c != '\n' for c in ko): return 'ctrl'
    return None

fix = json.load(open('_scene_tr_fix.json', encoding='utf-8'))
applied = 0; rej = 0
for fp in sorted(glob.glob('_repair_out/r*.json')):
    try: arr = json.load(open(fp, encoding='utf-8'))
    except Exception: continue
    if not isinstance(arr, list): continue
    for r in arr:
        if not isinstance(r, dict) or 'i' not in r: continue
        i = r['i']
        if i not in meta: continue
        ko = (r.get('ko') or '').strip('\x00')
        why = bad(meta[i]['jp'], ko, meta[i]['maxb'])
        if why: rej += 1; continue
        fix[str(i)] = ko; applied += 1
print(f"수리 반영 {applied} / 검증탈락 {rej}")
json.dump(fix, open('_scene_tr_fix.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('총 fix 항목', len(fix))
