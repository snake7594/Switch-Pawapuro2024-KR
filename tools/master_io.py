# -*- coding: utf-8 -*-
"""번역_마스터.json 읽기/쓰기 — 사람이 읽고 고칠 수 있는 '레코드 한 줄' 형식 유지.

한 줄짜리 거대 JSON은 편집기에서 열어도 볼 수가 없다. 그렇다고 indent를 주면
항목마다 여러 줄로 흩어져 용량이 몇 배가 된다. 그래서 절충안으로
  - 섹션(meta/exe/exe_ext/rdb)은 줄을 나누고
  - 항목 하나는 한 줄에 통째로
쓴다. 원하는 문구를 검색해 그 줄의 "ko" 만 고치면 된다.

사용:
    from master_io import load_master, save_master
    m = load_master()            # 기본 '번역_마스터.json'
    ...
    save_master(m)               # 형식 유지하며 저장
"""
import json

ORDER = ['meta', 'exe', 'exe_ext', 'rdb']
DEFAULT = '번역_마스터.json'

def load_master(path=DEFAULT):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save_master(m, path=DEFAULT):
    keys = [k for k in ORDER if k in m] + [k for k in m if k not in ORDER]
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('{\n')
        for i, k in enumerate(keys):
            v = m[k]
            f.write(' %s: ' % json.dumps(k, ensure_ascii=False))
            if isinstance(v, list):
                f.write('[\n')
                last = len(v) - 1
                for j, item in enumerate(v):
                    f.write('  ' + json.dumps(item, ensure_ascii=False) +
                            (',\n' if j < last else '\n'))
                f.write(' ]')
            else:
                f.write(json.dumps(v, ensure_ascii=False, indent=2).replace('\n', '\n '))
            f.write(',\n' if i < len(keys) - 1 else '\n')
        f.write('}\n')
