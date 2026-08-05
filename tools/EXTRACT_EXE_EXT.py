# -*- coding: utf-8 -*-
"""main-c(현재 배포 exe)의 마이라이프 확장 새영역에서 최종 문장을 역추출 →
마스터 exe_ext 섹션 생성. josa·line-fit 다 반영된 실제 배포본이 ground truth.
exe_ext 항목: {ko: 최종한글, ents: [frag별 ent_fpos 순서대로]}
  - ents[0] → 문장 VA 리다이렉트, ents[1:] → 빈문자열."""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSVR = {v: k for k, v in load_tsv().items()}
def dec(b):
    try: return ''.join(TSVR.get(c, c) for c in b.decode('utf-8'))
    except UnicodeDecodeError: return None

mc = open('inject_out/main-c', 'rb').read()
orig = open('main', 'rb').read()
def u32(f, o): return struct.unpack_from('<I', f, o)[0]
ROD_FO, ROD_MO = u32(mc, 0x20), u32(mc, 0x24); RO_DELTA = ROD_MO - ROD_FO
NEW_FO = u32(orig, 0x30); N = 0x100000; NEW_END = NEW_FO + N
def va2fo(va): return va - RO_DELTA

d = json.load(open('마이라이프_대사.json', encoding='utf-8'))
sents = [s for sc in d['scenes'] for s in sc['sentences'] if s['n_frag'] >= 2 and s['ko']]

exe_ext = []; skip = 0; empty_shared = None
for s in sents:
    ents = [f['ent_fpos'] for f in s['frags'] if f['ent_fpos'] is not None]
    if not ents: skip += 1; continue
    va = struct.unpack_from('<Q', mc, ents[0] + 16)[0]
    fo = va2fo(va)
    if not (NEW_FO <= fo < NEW_END): skip += 1; continue   # 리다이렉트 안 된 것
    e = mc.find(b'\x00', fo)
    ko = dec(mc[fo:e])
    if ko is None: skip += 1; continue
    exe_ext.append({'ko': ko, 'ents': ents})

# 무결성: dedup 문장 수 / ents 총수
uniq = len({x['ko'] for x in exe_ext})
tot_ents = sum(len(x['ents']) for x in exe_ext)
print(f"exe_ext 추출: {len(exe_ext)} 문장(고유 {uniq}), ents 총 {tot_ents}, 스킵 {skip}")

master = json.load(open('번역_마스터.json', encoding='utf-8'))
master['exe_ext'] = exe_ext
master['meta']['exe_ext_source'] = 'main-c 새영역 역추출(마이라이프 확장 완성문장). BUILD_FROM_MASTER.py로 재빌드.'
json.dump(master, open('번역_마스터.json', 'w', encoding='utf-8'), ensure_ascii=False)
print("마스터에 exe_ext 추가 저장 완료")
