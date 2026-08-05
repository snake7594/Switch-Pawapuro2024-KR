# -*- coding: utf-8 -*-
"""마이라이프 확장 리다이렉트 오탐 취소 → 마스터 exe_ext에서 제거.
씬 재구성이 '연속 RELA 슬롯의 독립 UI 항목·분기 대사'를 이어지는 대사 조각으로 오인 →
완성문장을 첫 슬롯에 몰고 나머지를 빈칸으로 만들어 화면이 깨지거나 멈춤.
취소 기준(확실한 것만):
  A. 완성문장 인자(%s/%d)가 첫 조각이 공급받는 인자를 초과/불일치 → 스택 오염(크래시)
  B. 완성문장이 대사창(3줄=72폭) 초과 → 버퍼/표시 초과
  E. 첫 조각이 공백 슬롯인데 완성문장을 주입 → 레이아웃 파손
취소 = exe_ext에서 제외 = 리다이렉트 안 함 = 원본 조각 그대로(master['exe'] 번역) 표시."""
import sys, os, json, re
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
from master_io import save_master   # 가독(레코드 한 줄) 형식 유지
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

FMT = re.compile(r'%[0-9.\-+ #]*([sdifgxXoucp])')
def is_full(c):
    o = ord(c)
    return (0x1100<=o<=0x11ff or 0xac00<=o<=0xd7a3 or 0x3000<=o<=0x30ff or 0x3400<=o<=0x9fff
            or 0xff00<=o<=0xff60 or 0xffe0<=o<=0xffe6 or 0x2e80<=o<=0x2fdf or 0xf900<=o<=0xfaff)
def width(s): return sum(1.0 if is_full(c) else 0.5 for c in s if c != '\n')

d = json.load(open('마이라이프_대사.json', encoding='utf-8'))
# ents[0] → 판정
def verdict(s):
    fj = [f['jp'] for f in s['frags']]; ko = s['ko']; f0 = fj[0] or ''
    ko_t = FMT.findall(ko); f0_t = FMT.findall(f0)
    if len(ko_t) > len(f0_t) or ko_t[:len(f0_t)] != f0_t: return 'A.인자시퀀스위반'
    if width(ko) > 72.0: return 'B.대사창초과'
    if not f0.strip(): return 'E.첫조각=공백슬롯'
    return None
cancel = {}
for sc in d['scenes']:
    for s in sc['sentences']:
        if s['n_frag'] < 2 or not s['ko']: continue
        ents = [f['ent_fpos'] for f in s['frags'] if f['ent_fpos'] is not None]
        if not ents: continue
        v = verdict(s)
        if v: cancel[ents[0]] = v

master = json.load(open('번역_마스터.json', encoding='utf-8'))
before = len(master['exe_ext'])
kept = [x for x in master['exe_ext'] if x['ents'][0] not in cancel]
removed = [x for x in master['exe_ext'] if x['ents'][0] in cancel]
master['exe_ext'] = kept
from collections import Counter
print("취소 사유별:", Counter(cancel[x['ents'][0]] for x in removed).most_common())
print(f"exe_ext {before} → {len(kept)} (취소 {len(removed)}건 = 원본 조각 표시로 복원)")
master['meta']['exe_ext_note'] = ('씬 재구성 오탐(UI항목/분기대사 뭉침) 취소분 제외. '
                                 '취소기준=인자시퀀스위반/대사창(72폭)초과/첫조각공백. CANCEL_BAD_EXT.py')
save_master(master)
json.dump([{'why': cancel[x['ents'][0]], 'ko': x['ko'], 'ents': x['ents']} for x in removed],
          open('_ext_cancelled.json', 'w', encoding='utf-8'), ensure_ascii=False)
print("마스터 갱신 완료 → BUILD_FROM_MASTER.py로 재빌드 필요")
