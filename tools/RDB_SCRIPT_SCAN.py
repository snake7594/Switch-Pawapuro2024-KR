# -*- coding: utf-8 -*-
"""RDB STRING청크 파일 중 '대본형'(문장이 연속 항목으로 이어짐) 파일 탐지.
utf8_00 테이블 순서에서 [끝에 종결부호 없음 & 가나] → [다음 항목이 이어짐꼴] 쌍 카운트."""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

def parse_utf8_table(b):
    """CHK 내 utf8_00 청크: base=태그+8+4(count)? 기존 추출과 동일 규칙(STRING+0x10, N=ptr[0]/4)."""
    out = []
    pos = 0
    while True:
        i = b.find(b'utf8_00\x00', pos)
        if i < 0: break
        base = i + 8
        try:
            sz = struct.unpack_from('<I', b, base)[0]
            n = struct.unpack_from('<I', b, base + 4)[0]
        except struct.error: break
        # 휴리스틱: [base+8 .. ] n개의 u32 오프셋 테이블일 수도, 아니면 NUL연속체
        pos = i + 8
        out.append((i, sz, n))
    return out

END = tuple('。！？」…♪）)!?～ー')
def kana(s): return any('぀' <= c <= 'ヿ' for c in s)

D = rdblib.RDB('.')
res = []
n = 0
import time; t0 = time.time()
for name, ent in D.idx.items():
    if ent['flag'] not in (0, 0x20): continue
    n += 1
    try: b = bytes(D.read_body(name))
    except Exception: continue
    if b'utf8_00\x00' not in b and b'STRING' not in b: continue
    # NUL-split 순서 기반(테이블 순서=저장 순서)
    segs = []
    pos = 0
    while pos < len(b):
        e = b.find(b'\x00', pos)
        if e < 0: break
        if 4 <= e - pos <= 400:
            try:
                s = b[pos:e].decode('utf-8')
                if s and not any(ord(c) < 0x20 for c in s): segs.append(s)
                else: segs.append(None)
            except UnicodeDecodeError: segs.append(None)
        else: segs.append(None)
        pos = e + 1
    cont = 0; total_jp = 0
    for a, c in zip(segs, segs[1:]):
        if not a or not c: continue
        if kana(a): total_jp += 1
        if kana(a) and kana(c) and len(a) >= 8 and not a.endswith(END):
            cont += 1
    if cont >= 10:
        res.append((name, cont, total_jp))
    if n % 3000 == 0: print(f'  {n} ({time.time()-t0:.0f}s)', flush=True)
D.close()
res.sort(key=lambda x: -x[1])
print('대본형 후보(연속쌍>=10):', len(res))
for name, cont, tj in res[:40]: print(f'  {name}: 이어짐 {cont} / 가나줄 {tj}')
json.dump(res, open('_rdb_script_files.json', 'w', encoding='utf-8'), ensure_ascii=False)
