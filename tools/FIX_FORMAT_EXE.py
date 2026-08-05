# -*- coding: utf-8 -*-
"""main-safe20 → main-safe21: exe 서식문자열(%-지정자) 손상 수리.
주입 단계에서 서식문자열이 잘못 절단/손상돼 printf 지정자 개수가 원본과 달라짐 → 인자 오독 → 크래시/멈춤.
수리: 각 서식문자열(jp에 % 포함) 위치에 **JSON의 정확한 ko를 지정자 보존하며 재주입**.
  - 전체 ko가 필드에 맞으면 그대로.
  - 초과면 지정자 토큰은 모두 보존하고 사이 텍스트만 절단.
  - 그래도 불가하면 원본 일본어 복원(지정자 정확·크래시 안전).
검증: 주입된 모든 서식문자열의 지정자 == 원본 jp 지정자."""
import sys, os, re, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import inject_lib as L

ENC = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv"))
orig = open(r'!exefs-작업/main-원본', 'rb').read()
buf = bytearray(open('inject_out/main-safe20', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)

FMT = re.compile(r'%[-+ 0-9.#]*[diouxXeEfgGcsp%]|％[ds]')
def tokens(s):
    """(리터럴/토큰) 분해, 토큰은 서식지정자."""
    out = []; i = 0
    for m in FMT.finditer(s):
        if m.start() > i: out.append(('lit', s[i:m.start()]))
        out.append(('fmt', m.group(0)))
        i = m.end()
    if i < len(s): out.append(('lit', s[i:]))
    return out
def spec_sig(s):
    return [t.replace('％', '%')[-1] for k, t in [(k, v) for k, v in [(x[0], x[1]) for x in tokens(s)]] if k == 'fmt' and t not in ('%%',)]
def sig(s):
    return [t[-1] for k, t in tokens(s) if k == 'fmt' and t.replace('％', '%') != '%%']

def enc_fit(ko, budget):
    """ko를 budget 바이트 내로 인코딩하되 서식토큰 전부 보존. 실패시 None."""
    b = ENC.encode(ko)
    if len(b) <= budget: return b
    # 지정자 보존 절단: 리터럴 조각을 뒤에서부터 줄임
    toks = tokens(ko)
    # 필수 = 모든 fmt 토큰(공백1개씩 이어붙일 최소). 리터럴은 축약 대상.
    def build(lits_keep):
        parts = []
        li = 0
        for k, v in toks:
            if k == 'fmt': parts.append(v)
            else:
                parts.append(v[:lits_keep] if len(v) > lits_keep else v)
        return ''.join(parts)
    # 리터럴 길이를 이진탐색으로 최대화
    lo, hi = 0, max((len(v) for k, v in toks if k == 'lit'), default=0)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = build(mid)
        eb = ENC.encode(cand)
        if len(eb) <= budget:
            best = eb; lo = mid + 1
        else:
            hi = mid - 1
    if best is not None:
        return best
    # 리터럴 0으로도 초과 → 지정자만 이어붙여도 초과
    onlyfmt = ''.join(v for k, v in toks if k == 'fmt')
    eb = ENC.encode(onlyfmt)
    return eb if len(eb) <= budget else None

doc = json.load(open('번역_일본어.json', encoding='utf-8'))
n_fix = n_revert = n_ok = 0
mismatch_after = 0
for s in doc['strings']:
    jp = s['jp']; ko = s.get('ko', '').strip()
    if '%' not in jp and '％' not in jp: continue
    jsig = sig(jp)
    if not jsig: continue
    for occ in s.get('occurrences', []):
        if occ['method'] != 'exe': continue
        off = occ['offset']
        e = buf.find(b'\x00', off)
        if e < 0: continue
        # 현재 주입 상태 지정자
        cur = bytes(buf[off:e])
        # 필드 예산(원본 기준 슬랙)
        oe = orig.find(b'\x00', off)
        T = 0; k = oe
        while k < len(orig) and orig[k] == 0: T += 1; k += 1
        budget = (oe - off) + (T - 1 if T > 0 else 0)
        # 목표: ko(지정자=jsig). ko 지정자가 jp와 다르면 ko는 신뢰불가 → 원문
        use_ko = ko and sig(ko) == jsig
        nb = None
        if use_ko:
            nb = enc_fit(ko, budget)
            if nb is not None and sig(nb.decode('utf-8', 'ignore')) != jsig:
                nb = None
        if nb is None:
            # 원본 일본어 복원(지정자 정확)
            jb = jp.encode('utf-8')
            if len(jb) <= budget:
                nb = jb;
            else:
                # 지정자 보존 절단(일본어)
                nb2 = enc_fit(jp, budget)  # 일본어엔 한글 없어 그대로 인코딩됨
                nb = nb2
            n_revert += 1
        else:
            n_fix += 1
        region = (oe - off) + T
        buf[off:off+len(nb)] = nb
        buf[off+len(nb):off+region] = b'\x00' * (region - len(nb))
        # 검증
        fe = buf.find(b'\x00', off)
        if sig(bytes(buf[off:fe]).decode('utf-8', 'ignore')) != jsig:
            mismatch_after += 1
print(f"서식 재주입: 수정 {n_fix}, 원문복원 {n_revert}, 수리후 잔여 불일치 {mismatch_after}")

# 무결성: safe20 기준(동적영역 무변경) + 원본기준(.text/헤더 불변)
import numpy as np
base20 = np.frombuffer(open('inject_out/main-safe20', 'rb').read(), dtype=np.uint8)
an = np.frombuffer(bytes(buf), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
DYN_LO, DYN_HI = 0x2aafb79, 0x3d2551d
new = np.nonzero(base20 != an)[0]              # FIX_FORMAT이 바꾼 것
in_tx = int(((new >= tx_fo) & (new < tx_fo + tx_sz)).sum())
in_hdr = int((new < 0x100).sum())
in_dyn = int(((new >= DYN_LO) & (new < DYN_HI)).sum())
print(f"safe20→safe21 변경 {len(new)}B: .text {in_tx} 헤더 {in_hdr} 동적영역 {in_dyn} (모두 0이어야)")
assert in_tx == 0 and in_hdr == 0 and in_dyn == 0 and len(buf) == len(orig)
open('inject_out/main-safe21', 'wb').write(bytes(buf))
print("저장 inject_out/main-safe21 (동적영역=safe6 유지 → 부팅안전 + 서식 수리)")
