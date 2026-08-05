# -*- coding: utf-8 -*-
"""_recode_plan.json 후처리: 원본(jp) 문자열 기준 교정.
- 이름읽기 오역 교정(비 NAME_DIC): 優勝→우승, 月火水木金土→월화수목금토, あき→공석
- ko 부분열 교정: 이노가리→이가리 (전 파일)
원본 슬롯을 다시 읽어 각 패치 오프셋의 org 문자열을 확인 후 해당 패치만 교체."""
import sys, os, json
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
TSV = load_tsv()
TSV_R = {v: k for k, v in TSV.items()}
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def dec_tsv(b):
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: return None
    return ''.join(TSV_R.get(c, c) for c in s)

ORG_CORR = {'優勝': '우승', '月': '월', '火': '화', '水': '수', '木': '목',
            '金': '금', '土': '토', 'あき': '공석'}
KO_SUB = [('이노가리', '이가리')]

plans = json.load(open('_recode_plan.json', encoding='utf-8'))
ORG = rdblib.RDB('.')
n_org = n_sub = 0
for name, plan in plans.items():
    if name == 'NAME_DIC.CHK': continue
    if not plan.get('patches'): continue
    org = None
    newp = []
    for off, region, hexs in plan['patches']:
        nb = bytes.fromhex(hexs)
        # ko 부분열 교정
        d = dec_tsv(nb)
        changed = False
        if d:
            d2 = d
            for a, b in KO_SUB:
                if a in d2: d2 = d2.replace(a, b)
            if d2 != d:
                nb = enc(d2); changed = True; n_sub += 1
        # org 기준 교정
        if plan.get('aligned', True):
            if org is None:
                try: org = ORG.read_body(name)
                except Exception: org = b''
            if org and off < len(org):
                e = org.find(b'\x00', off)
                if e > off:
                    try: ojp = org[off:e].decode('utf-8')
                    except UnicodeDecodeError: ojp = None
                    if ojp in ORG_CORR:
                        nb = enc(ORG_CORR[ojp]); changed = True; n_org += 1
        if changed and len(nb) > region - 1:
            nb = nb[:region-1]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
        newp.append([off, region, nb.hex()])
    plan['patches'] = newp
ORG.close()
json.dump(plans, open('_recode_plan.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"교정 완료: org기준 {n_org}건, ko부분열 {n_sub}건")
