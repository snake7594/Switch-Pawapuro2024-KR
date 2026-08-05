# -*- coding: utf-8 -*-
"""PASS1(읽기 전용): 배포 RDB(repack_out) vs 원본 RDB(root) 전 텍스트 슬롯 분석.
수집:
 A) 재인코딩 대상: 주입 문자열(원본과 다른 NUL경계 세그먼트, wReplace 역디코드시 한글≥50%)
    → wReplace→tsv 재인코딩 계획 (+ ·→・, —→ー 문자수정)
 B) 사전 주입 대상: 미번역 JP 문자열(원본과 동일) 중 사전(jp→ko) 매칭
 C) 미지 대상: 사전에 없는 미번역 JP → 워크플로 번역용 수집
출력: _recode_plan.json (슬롯별 패치계획), _sweep_unknown.json (미지 JP)
"""
import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m

def load_w():
    m = {}
    txt = open('!폰트작업/실황2024.wReplace', 'rb').read().decode('utf-16')
    for ln in txt.splitlines():
        ln = ln.lstrip('﻿')
        if ln.startswith('#'): continue
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m

TSV = load_tsv()
WREP = load_w()
WREP_R = {v: k for k, v in WREP.items()}
DICT = json.load(open('_dict_jpko.json', encoding='utf-8'))
KNOWN_KO = set(json.load(open('_known_ko.json', encoding='utf-8')))

def is_hangul(c): return '가' <= c <= '힣'
def has_jp(s):
    return any(('぀' <= c <= 'ヿ') or ('一' <= c <= '鿿') for c in s)
def charfix(s): return s.replace('·', '・').replace('—', 'ー')

def enc_tsv(ko):
    return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

def dec_wrep(txt):
    return ''.join(WREP_R.get(c, c) for c in txt)

def walk_strings(body):
    """NUL경계 세그먼트 (start, end, bytes) — UTF-8 텍스트만."""
    out = []
    pos = 0; L = len(body)
    while pos < L:
        e = body.find(b'\x00', pos)
        if e < 0: e = L
        if e - pos >= 4:
            seg = body[pos:e]
            try:
                s = seg.decode('utf-8')
                if s and not any(ord(c) < 9 or 11 <= ord(c) <= 31 for c in s):
                    out.append((pos, e, s))
            except UnicodeDecodeError:
                pass
        pos = e + 1
    return out

sweep = set(json.load(open('_sweep_files.json', encoding='utf-8')))
# NXSUR 타깃 등 추가 목록
for extra in ('npb_nxsur_targets.txt',):
    if os.path.isfile(extra):
        for ln in open(extra, encoding='utf-8'):
            ln = ln.strip()
            if ln: sweep.add(ln)
sweep.discard('COMMON_2D.CHK'); sweep.discard('COMMON_2D_ADD.CHK')

DEP = rdblib.RDB('repack_out')
ORG = rdblib.RDB('.')

plans = {}          # name -> {'aligned':bool, 'patches':[(off, old_len_region, new_hex)], ...}
unknown = {}        # jp -> {'occ': [(name, off, budget)], 'n': count}
stats = dict(files=0, err=0, re_enc=0, dictinj=0, unk=0, mixed_warn=0, noalign=0)
t0 = time.time()

names = sorted(sweep)
for idx, name in enumerate(names):
    if name not in DEP.idx or name not in ORG.idx: continue
    try:
        dep = DEP.read_body(name); org = ORG.read_body(name)
    except Exception:
        stats['err'] += 1; continue
    if dep is None or org is None: continue
    stats['files'] += 1
    aligned = len(dep) == len(org)
    patches = []
    segs = walk_strings(dep)
    for (s, e, txt) in segs:
        if aligned:
            injected = dep[s:e] != org[s:e]
        else:
            # 비정렬(재구축 STRING/SEN_TEXT — 절단 없음): 디코드가 알려진 번역과 정확 일치할 때만 주입 판정
            dec0 = dec_wrep(txt)
            injected = (dec0 != txt) and (dec0 in KNOWN_KO)
        if injected:
            # (A) 주입 문자열 후보 → 재인코딩
            dec = dec_wrep(txt)
            n_h = sum(1 for c in dec if is_hangul(c))
            cjk = sum(1 for c in txt if '一' <= c <= '鿿')
            if n_h == 0 or cjk == 0:
                continue  # 한글 디코드 안 됨(ASCII 등) → 스킵
            if n_h < cjk * 0.5:
                stats['mixed_warn'] += 1; continue
            ko = charfix(dec)
            nb = enc_tsv(ko)
            # 슬랙 계산(뒤 NUL런)
            T = 0; k = e
            while k < len(dep) and dep[k] == 0: T += 1; k += 1
            cap = (e - s) + (T - 1 if T > 0 else 0)
            if len(nb) > cap:
                nb2 = enc_tsv(charfix(dec).replace(' ', ''))
                nb = nb2 if len(nb2) <= cap else nb[:cap]
                while nb:
                    try: nb.decode('utf-8'); break
                    except UnicodeDecodeError: nb = nb[:-1]
            patches.append((s, e - s + T, nb.hex()))
            stats['re_enc'] += 1
        else:
            # (B/C) 미번역 JP
            if not has_jp(txt) or len(txt) < 2: continue
            ko = DICT.get(txt)
            T = 0; k = e
            while k < len(dep) and dep[k] == 0: T += 1; k += 1
            cap = (e - s) + (T - 1 if T > 0 else 0)
            if ko:
                nb = enc_tsv(charfix(ko))
                if len(nb) > cap:
                    nb2 = enc_tsv(charfix(ko).replace(' ', ''))
                    nb = nb2 if len(nb2) <= cap else nb[:cap]
                    while nb:
                        try: nb.decode('utf-8'); break
                        except UnicodeDecodeError: nb = nb[:-1]
                if nb:
                    patches.append((s, e - s + T, nb.hex()))
                    stats['dictinj'] += 1
            else:
                u = unknown.setdefault(txt, {'occ': [], 'n': 0})
                u['occ'].append((name, s, cap))
                u['n'] += 1
                stats['unk'] += 1
    if not aligned: stats['noalign'] += 1
    if patches:
        plans[name] = {'aligned': aligned, 'patches': patches}
    if idx % 500 == 0:
        print(f'  {idx}/{len(names)} files, re_enc {stats["re_enc"]}, dict {stats["dictinj"]}, unk고유 {len(unknown)} ({time.time()-t0:.0f}s)', flush=True)

DEP.close(); ORG.close()
json.dump(plans, open('_recode_plan.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({k: v for k, v in unknown.items()}, open('_sweep_unknown.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('=' * 60)
print(f"완료 {time.time()-t0:.0f}s: {stats}")
print(f"패치계획 슬롯 {len(plans)}, 미지 고유 JP {len(unknown)}")
