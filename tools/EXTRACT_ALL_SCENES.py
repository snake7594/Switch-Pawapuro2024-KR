# -*- coding: utf-8 -*-
"""마이라이프 대사 추출 → 마이라이프_대사.json
- 씬(_scenes) 중 마이라이프(키워드 or VA구간)를 문장 단위로 조립
- 각 문장: 조립 jp + 조각별 {jp, str_off, str_va, ent_fpos(RELA엔트리 파일위치), r_offset}
  → 리다이렉트: 첫 조각 ent addend=새문장VA, 나머지=빈문자열VA
- ko 빈칸(번역 채움), ml_score(키워드수), 화자힌트"""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

b = open('main', 'rb').read()
RO_FO, RO_MO = 0x2aafb21, 0x2ab0000
DELTA = RO_MO - RO_FO
def va2fo(va): return va - DELTA
def fo2va(fo): return fo + DELTA
F, M = RO_FO, RO_MO
RELA_F = 0x2ab0058 - M + F; RELA_CNT = 0xc36e2
rela = np.frombuffer(b[RELA_F:RELA_F+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
roff = rela[:, 0]
# r_offset → RELA 엔트리 인덱스 (빠른 조회)
roff_sorted_idx = np.argsort(roff, kind='stable')
roff_sorted = roff[roff_sorted_idx]
def ent_fpos_of(r_offset):
    j = int(np.searchsorted(roff_sorted, r_offset))
    if j < len(roff_sorted) and roff_sorted[j] == r_offset:
        return RELA_F + 24 * int(roff_sorted_idx[j])
    return None

scenes = json.load(open('_scenes.json', encoding='utf-8'))
frag = set(json.load(open('_frag_sids.json')))
# 마이라이프 고유 키워드(범용어 応援/練習/試合/球団 제외)
ML_KW = ['入団会見', '契約更改', '年俸', '寮長', 'マイライフ', '入寮', 'オフの日', 'デート',
         '救世主', 'オッサン', 'ミゾット', 'サブポジ', '代理人', '選手寿命', '監督契約',
         '結婚', '引退試合', 'たんぽぽ', 'アンヌ', 'ヌシ', 'わらわ', '成仏', 'クサれ縁']
END = tuple('。！？」…♪')
KANA = lambda s: any('぀' <= c <= 'ヿ' for c in s)
import re as _re
_RUBY = _re.compile(r'^(.+?)／[぀-ゟ゠-ヿー]+$')
def clean_frag(jp):
    """루비 슬롯(단어／かな) → 앞 단어만. 조립 문장을 깨끗하게."""
    m = _RUBY.match(jp)
    return m.group(1) if m else jp

def is_dialogue_scene(sc):
    """UI/메뉴 목록 배제: 회화체 지표(종결부호율·가나율)."""
    ls = [x for x in sc['lines'] if x and x['jp']]
    if len(ls) < 3: return False
    punct = sum(1 for x in ls if any(c in x['jp'] for c in '。！？…、')) / len(ls)
    kana = sum(1 for x in ls if KANA(x['jp'])) / len(ls)
    return punct >= 0.20 and kana >= 0.5

out = []
n_sent = 0; n_frag_sent = 0
for sc in scenes:
    # 조각형 여부 무관 — 모든 마이라이프 대사 씬 대상(조각 조합 문장이 핵심)
    jps = ' '.join(x['jp'] for x in sc['lines'] if x)
    if 'デバッグ' in jps or 'ショートカット設定判定' in jps: continue  # 개발용 디버그 씬 제외
    score = sum(1 for kw in ML_KW if kw in jps)
    if not is_dialogue_scene(sc): continue  # UI/목록 배제 (회화체만)
    in_va = True
    stride = sc['stride']; va0 = sc['slot_va0']
    # 메뉴 선택지 조각(종결부호 없이 완결) = 문장 경계로도 취급
    MENU_END = _re.compile(r'(しない|します|する|した|ます|ません|できる|ください|）|\)|１軍）?|２軍）?)$')
    sentences = []
    cur = []
    for k, x in enumerate(sc['lines']):
        if x is None:
            continue
        r_off = va0 + k * stride
        efp = ent_fpos_of(r_off)
        jp = x['jp']
        cur.append({'jp': jp, 'str_off': x['foff'], 'str_va': int(fo2va(x['foff'])),
                    'r_offset': int(r_off), 'ent_fpos': efp})
        jr = jp.rstrip()
        if jr.endswith(END) or MENU_END.search(jr):   # 종결부호 or 메뉴선택지 완결
            sentences.append(cur); cur = []
    if cur: sentences.append(cur)
    # 문장 레코드 — 회화체 대사만(옵션/설명체 배제)
    CONVO_MARK = '「」『』！？♪…〜～'
    CONVO_END = ('でやんす', 'だよ', 'だね', 'だぞ', 'なの', 'のよ', 'わよ', 'かな', 'よね', 'じゃん',
                 'ジャン', 'っ', 'ぞ', 'ぜ', 'ね', 'よ', 'さ', 'わ', 'な', 'い', 'ろ', 'け')
    SETSU = ('します。', 'します', 'にします。', 'できます。', 'されます。', 'ください。', '表示', '設定')
    sents = []
    for frags in sentences:
        jp_full = ''.join(clean_frag(f['jp']) for f in frags)   # 루비 제거한 깨끗한 조립
        if not jp_full.rstrip().endswith(END): continue
        if not KANA(jp_full): continue
        if len(frags) > 12: continue
        if len(jp_full) < 4: continue
        body = jp_full.rstrip('。！？」…♪　 ')
        convo = any(c in jp_full for c in CONVO_MARK) or body.endswith(CONVO_END)
        has_kw = any(kw in jp_full for kw in ML_KW)
        # 순수 설명/옵션체(회화표지 없고 키워드 없고 '～します' 류)면 제외
        if not convo and not has_kw:
            if any(jp_full.rstrip().endswith(s) or s in jp_full[-8:] for s in ('します。', 'できます。', 'されます。', 'ください。')):
                continue
            if jp_full.rstrip().endswith('です。') and '「' not in jp_full:
                continue
        n_sent += 1
        if len(frags) >= 2: n_frag_sent += 1
        sents.append({'jp': jp_full, 'ko': '', 'n_frag': len(frags), 'frags': frags,
                      'convo': convo, 'has_kw': has_kw})
    if not sents: continue
    out.append({'run_id': sc['run_id'], 'slot_va0': int(va0), 'stride': stride,
                'ml_score': score, 'in_va_cluster': in_va, 'sentences': sents})

# 엔트리 매핑 성공률 점검
tot_frag = sum(len(s['frags']) for sc in out for s in sc['sentences'])
mapped = sum(1 for sc in out for s in sc['sentences'] for f in s['frags'] if f['ent_fpos'] is not None)
doc = {
    'meta': {
        'note': '마이라이프 대사(문장 단위 조립). 리다이렉트: 각 sentence의 frags[0].ent_fpos+16에 새 문장VA, frags[1:].ent_fpos+16에 빈문자열VA. ko를 채워 번역.',
        'scenes': len(out), 'sentences': n_sent, 'multi_frag_sentences': n_frag_sent,
        'frag_entry_mapped': f'{mapped}/{tot_frag}',
    },
    'scenes': out,
}
json.dump(doc, open('전체대사_재구성.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"씬 {len(out)} / 문장 {n_sent} (2조각+ {n_frag_sent}) / 엔트리매핑 {mapped}/{tot_frag}")
print(f"→ 마이라이프_대사.json ({os.path.getsize('전체대사_재구성.json')/1024:.0f}KB)")
# 표본
for sc in out[:2]:
    print('--- 씬', sc['run_id'], 'ml_score', sc['ml_score'])
    for s in sc['sentences'][:3]:
        print('   [%d조각]' % s['n_frag'], repr(s['jp'][:44]))
