# -*- coding: utf-8 -*-
"""루비/가나 잔존 교정(_ruby_fix_out) 검증 → 번역_마스터.json에 반영.
검증: 가나·／ 잔존 없음, maxb 이내, spec/tag 보존. 통과분만 마스터 ko 갱신."""
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

rows = json.load(open('_ruby_leftover.json', encoding='utf-8'))
SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|%%')
TAG = re.compile(r'<[^<>\n]{1,24}>')
KANA = re.compile(r'[぀-ゟ゠-ヿ]')
ALLOW = set('ー・～')
def bad(jp, ko, mb):
    if not ko: return 'empty'
    if '／' in ko and '／' not in jp: return 'slash'
    if any(KANA.match(c) and c not in ALLOW for c in ko): return 'kana'
    if any('가' <= c <= '힣' and c not in TSV for c in ko): return 'syl'
    if sorted(SPEC.findall(jp)) != sorted(SPEC.findall(ko)): return 'spec'
    if sorted(TAG.findall(jp)) != sorted(TAG.findall(ko)): return 'tag'
    if len(enc(ko)) > mb: return 'len'
    return None

fixes = {}
for fp in sorted(glob.glob('_ruby_fix_out/r*.json')):
    try: arr = json.load(open(fp, encoding='utf-8'))
    except Exception: continue
    for r in arr:
        if isinstance(r, dict) and 'k' in r: fixes[r['k']] = (r.get('ko') or '').strip('\x00')

# 마스터 로드 + 인덱스(off / file,off)
master = json.load(open('번역_마스터.json', encoding='utf-8'))
exe_idx = {r['off']: r for r in master['exe']}
rdb_idx = {(r['file'], r['off']): r for r in master['rdb']}

applied = 0; rej = {}; still = 0
for k, r in enumerate(rows):
    ko = fixes.get(k)
    if ko is None: continue
    why = bad(r['jp'], ko, r['maxb'])
    if why:
        rej[why] = rej.get(why, 0) + 1
        # 폴백: 최소한 ／이후 제거 + 가나 제거 시도
        alt = ko.split('／')[0]
        alt = ''.join(c for c in alt if not (KANA.match(c) and c not in ALLOW))
        if not bad(r['jp'], alt, r['maxb']) and alt:
            ko = alt
        else:
            still += 1; continue
    if r['src'] == 'exe':
        t = exe_idx.get(r['off'])
        if t: t['ko'] = ko; applied += 1
    else:
        t = rdb_idx.get((r['file'], r['off']))
        if t: t['ko'] = ko; applied += 1
json.dump(master, open('번역_마스터.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"마스터 반영 {applied} / 검증탈락 {dict(rej)} / 최종실패 {still}")
