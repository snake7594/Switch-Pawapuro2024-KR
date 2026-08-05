# -*- coding: utf-8 -*-
"""마이라이프 리다이렉트 (확장 새영역 사용) → main-mylife-exp.
- 베이스: main-expand (EXPAND_NSO로 rodata +N 확장, data/bss 재배치됨)
- 새 영역(rodata 확장부, 아무도 안 쓰는 진짜 빈 공간)에 문장 기록 → 리다이렉트
- 죽은풀 대신 새 영역이라 셰이더/리소스 침범 없음
- 리다이렉트 엔트리 ent_fpos는 rodata 앞부분(재배치 무영향)이라 유효, addend(+16)에 새 문장 VA"""
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
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

BASE = sys.argv[1] if len(sys.argv) > 1 else 'inject_out/main-expand'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'inject_out/main-mylife-exp'
N = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x100000
buf = bytearray(open(BASE, 'rb').read())
orig = open('main', 'rb').read()   # ent_fpos·조각 원문 검증용(원본 RELA 기준)
def u32(f, o): return struct.unpack_from('<I', f, o)[0]
ROD_FO, ROD_MO = u32(bytes(buf), 0x20), u32(bytes(buf), 0x24)
RO_DELTA = ROD_MO - ROD_FO
# 새 영역: 확장 삽입 위치 = 원본 data FileOff (=현재 rodata 끝 직전 삽입 구간)
NEW_FO = u32(orig, 0x30)          # 원본 data FileOff = 새 영역 파일 시작
NEW_END = NEW_FO + N
def fo2va(fo): return fo + RO_DELTA
print(f"새 영역 파일 [{hex(NEW_FO)},{hex(NEW_END)}) VA {hex(fo2va(NEW_FO))}~")

d = json.load(open('전체대사_재구성.json', encoding='utf-8'))
sents = [s for sc in d['scenes'] for s in sc['sentences'] if s['n_frag'] >= 2 and s['ko']]
# dedup 문장 → 새 영역 순차 배치
cur = NEW_FO
buf[cur:cur+1] = b'\x00'; empty_va = fo2va(cur); cur += 1   # 빈문자열
enc_map = {}
for eb in sorted({enc(s['ko']) for s in sents}, key=lambda x: -len(x)):
    if cur + len(eb) + 1 > NEW_END: raise SystemExit(f"새 영역 부족: N 늘려라 (need>{hex(N)})")
    buf[cur:cur+len(eb)] = eb; buf[cur+len(eb)] = 0
    enc_map[eb] = fo2va(cur); cur += len(eb) + 1
used = cur - NEW_FO
print(f"문장 dedup {len(enc_map)} 기록, 새 영역 사용 {used}B / {N}B")

stats = dict(redir=0, empt=0)
for s in sents:
    eb = enc(s['ko']); va = enc_map[eb]
    fr = s['frags']
    if fr[0]['ent_fpos'] is None: continue
    struct.pack_into('<Q', buf, fr[0]['ent_fpos']+16, va); stats['redir'] += 1
    for f in fr[1:]:
        if f['ent_fpos'] is None: continue
        struct.pack_into('<Q', buf, f['ent_fpos']+16, empty_va); stats['empt'] += 1
open(OUT, 'wb').write(bytes(buf))
import hashlib
print(f"주입 {stats} → {OUT}  md5 {hashlib.md5(bytes(buf)).hexdigest()}")
