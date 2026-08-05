# -*- coding: utf-8 -*-
"""수리 웨이브 병합: _scene_fix_out/f*.json → 재검증 통과분 _scene_tr_fix.json
통과 못한 항목은 안전 폴백: 기존 ko를 UTF-8 경계에서 클린 절단(maxb) / nl 불일치는 \n 강제 조정."""
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

bad = json.load(open('_scene_tr_bad.json', encoding='utf-8'))
SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|%%')
TAG = re.compile(r'<[^<>\n]{1,24}>')
KANA = re.compile(r'[぀-ゟ゠-ヿ]')
ALLOW_KANA = set('ー・～')

def valid(jp, ko, maxb):
    if not ko: return 'empty'
    if sorted(SPEC.findall(jp)) != sorted(SPEC.findall(ko)): return 'spec'
    if sorted(TAG.findall(jp)) != sorted(TAG.findall(ko)): return 'tag'
    if jp.count('\n') != ko.count('\n'): return 'nl'
    if any(KANA.match(c) and c not in ALLOW_KANA for c in ko): return 'kana'
    if any('가' <= c <= '힣' and c not in TSV for c in ko): return 'syl'
    if len(enc(ko)) > maxb: return 'len'
    if any(ord(c) < 0x20 and c != '\n' for c in ko): return 'ctrl'
    return None

fix = {}
seen = set()
for fp in sorted(glob.glob('_scene_fix_out/f*.json')):
    try: arr = json.load(open(fp, encoding='utf-8'))
    except Exception: continue
    for r in arr:
        if not isinstance(r, dict) or 'i' not in r: continue
        k = str(r['i'])
        if k not in bad or k in seen: continue
        seen.add(k)
        jp = bad[k]['jp']; maxb = bad[k]['maxb']
        ko = (r.get('ko') or '').strip('\x00')
        if valid(jp, ko, maxb) is None: fix[k] = ko

# 폴백: 남은 불량은 규칙 기반 수리
fb = 0
for k, v in bad.items():
    if k in fix: continue
    jp, ko, maxb = v['jp'], v['ko'], v['maxb']
    if not ko: continue
    # nl 조정: 부족하면 끝에 추가 불가 → 초과 \n 제거 / 부족 \n은 중간 공백을 개행으로
    dn = jp.count('\n') - ko.count('\n')
    if dn < 0: ko = ko.replace('\n', ' ', -dn)
    elif dn > 0:
        parts = ko.split(' ')
        while dn > 0 and len(parts) > 1:
            mid = len(parts) // 2
            parts[mid-1] = parts[mid-1] + '\n' + parts.pop(mid); dn -= 1
        ko = ' '.join(parts)
        if dn > 0: ko = ko + '\n' * dn
    # 가나/비표준 음절 제거 불가시 스킵
    if any(KANA.match(c) and c not in ALLOW_KANA for c in ko): continue
    if any('가' <= c <= '힣' and c not in TSV for c in ko): continue
    # 길이: UTF-8 경계 클린 절단
    nb = enc(ko)
    if len(nb) > maxb:
        nb = nb[:maxb]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
        # 역디코드해 ko 재구성(tsv 역변환)
        TSVR = {vv: kk for kk, vv in TSV.items()}
        ko = ''.join(TSVR.get(c, c) for c in nb.decode('utf-8'))
    if valid(jp, ko, maxb) is None:
        fix[k] = ko; fb += 1
print(f"수리 병합 {len(fix):,} (에이전트 {len(fix)-fb:,} + 폴백 {fb:,}) / 불량 {len(bad):,}")
json.dump(fix, open('_scene_tr_fix.json', 'w', encoding='utf-8'), ensure_ascii=False)
rest = [k for k in bad if k not in fix]
print('잔여 미수리', len(rest))
json.dump(rest, open('_scene_fix_rest.json', 'w'))
