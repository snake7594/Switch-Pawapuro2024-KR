# -*- coding: utf-8 -*-
"""씬 번역 입력 빌드: _scenes.json → _scene_tr_input.json
- 대사 씬(4+라인, 평균7자+, 구두점35%+)만
- 유니크 문자열(foff 기준) 첫 등장 씬이 소유(id 부여), 재등장은 ctx(번역 불요)
- budget: 원본 바이트 예산(세그+후행NUL-1)"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
scenes = json.load(open('_scenes.json', encoding='utf-8'))

def is_dialogue(sc):
    ls = [x for x in sc['lines'] if x and x['jpish']]
    if len(ls) < 4: return False
    avg = sum(len(x['jp']) for x in ls) / len(ls)
    punct = sum(1 for x in ls if any(c in x['jp'] for c in '。！？…、')) / len(ls)
    return avg >= 7 and punct >= 0.35

own = {}   # foff -> uid
out = []
uid = 0
n_own = n_ctx = 0
for sc in scenes:
    if not is_dialogue(sc): continue
    lines = []
    for x in sc['lines']:
        if not x: continue
        if not x['jpish']:
            lines.append({'t': 'lbl', 'jp': x['jp'][:40]})
            continue
        fo = x['foff']
        if fo in own:
            lines.append({'t': 'ctx', 'jp': x['jp']})
            n_ctx += 1
        else:
            own[fo] = uid
            lines.append({'t': 'tr', 'i': uid, 'jp': x['jp'], 'maxb': x['budget'], 'foff': fo})
            uid += 1
            n_own += 1
    out.append({'sid': sc['run_id'], 'lines': lines})
print(f"씬 {len(out)}, 번역대상 {n_own:,}, ctx 재등장 {n_ctx:,}")
json.dump(out, open('_scene_tr_input.json', 'w', encoding='utf-8'), ensure_ascii=False)
# 배치 분할 계획: 씬 경계 유지, 배치당 ~600 tr 라인
batches = []
cur = []; cnt = 0
for sc in out:
    k = sum(1 for l in sc['lines'] if l['t'] == 'tr')
    if cnt + k > 600 and cur:
        batches.append(cur); cur = []; cnt = 0
    cur.append(sc['sid']); cnt += k
if cur: batches.append(cur)
json.dump(batches, open('_scene_batches.json', 'w', encoding='utf-8'))
print(f"배치 {len(batches)}개 (씬경계 유지, ~600라인/배치)")
