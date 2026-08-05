# -*- coding: utf-8 -*-
"""줄규칙 정비 결과를 마스터에 반영(텍스트 단일 소스 유지).
- exe: _line_apply.json(off→축약ko) 교체 + 조사병기 확정(resolve)
- rdb: _rdb_fit_ok.json(file,off→축약ko) 교체
백업: 번역_마스터.json → 번역_마스터.bak_linefit.json"""
import sys, os, json, re, shutil
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
from master_io import save_master   # 가독(레코드 한 줄) 형식 유지
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

def has_batchim(ch):
    if not ('가' <= ch <= '힣'): return None
    return (ord(ch) - 0xAC00) % 28 != 0
PAIRS = [('이(가)','이','가'),('가(이)','이','가'),('을(를)','을','를'),('를(을)','을','를'),
         ('은(는)','은','는'),('는(은)','은','는'),('과(와)','과','와'),('와(과)','과','와'),
         ('이／가','이','가'),('을／를','을','를'),('은／는','은','는'),('과／와','과','와'),('와／과','과','와')]
PAT = re.compile('(' + '|'.join(re.escape(p[0]) for p in PAIRS) + ')')
LOOK = {p[0]: (p[1], p[2]) for p in PAIRS}
def resolve(ko):
    out=[]; i=0; changed=False
    for m in PAT.finditer(ko):
        s,e=m.span(); tok=m.group(1); prev=ko[s-1] if s>0 else ''; bat=has_batchim(prev); chosen=None
        if bat is not None and tok in LOOK:
            b1,b0=LOOK[tok]; chosen=b1 if bat else b0
        out.append(ko[i:s]); out.append(chosen if chosen else tok); i=e
        if chosen: changed=True
    out.append(ko[i:]); return ''.join(out)

master = json.load(open('번역_마스터.json', encoding='utf-8'))
shutil.copy('번역_마스터.json', '번역_마스터.bak_linefit.json')

# exe: off별 축약 교체
line_apply = dict(json.load(open('_line_apply.json', encoding='utf-8')))
ce=0; cj=0
for r in master['exe']:
    off = r['off']
    if off in line_apply and r['ko'] != line_apply[off]:
        r['ko'] = line_apply[off]; ce += 1
    nk = resolve(r['ko'])
    if nk != r['ko']: r['ko'] = nk; cj += 1
print(f"exe: line교체 {ce}, 조사확정 {cj}")

# rdb: (file,off)별 축약 교체
ok = json.load(open('_rdb_fit_ok.json', encoding='utf-8'))
fitmap = {(x['file'], x['off']): x['ko_new'] for x in ok}
cr=0
for r in master['rdb']:
    k = (r['file'], r['off'])
    if k in fitmap and r['ko'] != fitmap[k]:
        r['ko'] = fitmap[k]; cr += 1
print(f"rdb: 축약교체 {cr}")

save_master(master)
print("마스터 갱신 완료 → 번역_마스터.json")
