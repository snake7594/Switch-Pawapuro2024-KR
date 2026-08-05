# -*- coding: utf-8 -*-
import json, re

IN = '_1to1_in/s124.json'
OUT = '_1to1_out/s124.json'

data = json.load(open(IN, encoding='utf-8'))
scene = data[0]
lines = scene['lines']

slots = [l for l in lines if 'i' in l]
print("total slots:", len(slots))

# ---------------------------------------------------------------
# Master ability-name glossary (base JP -> base KO), used to build
# the "○○の本" / "○○になります" / "○○になった" template families.
# ---------------------------------------------------------------
ABILITY = {
 "打たれ強さ":"피안타내성","対ピンチ":"위기대응","対左打者":"좌타자전",
 "ノビ":"볼끝","キレ○":"예리○","クイック":"퀵모션",
 "調子安定（投手）":"상태안정(투수)","調子極端（投手）":"상태극단(투수)",
 "回復":"회복","打球反応○":"타구반응○","牽制○":"견제○",
 "ポーカーフェイス":"포커페이스","闘志":"투지","低め○":"저구○",
 "重い球":"묵직구","尻上がり":"후반상승","ジャイロボール":"자이로볼",
 "逃げ球":"도피구","リリース○":"릴리스○","奪三振":"탈삼진",
 "威圧感":"위압감","緊急登板○":"긴급등판○","球速安定":"구속안정",
 "内角攻め":"몸쪽공략","回またぎ○":"연투○","人気者":"인기남",
 "対強打者○":"강타전○","根性○":"근성○","クロスファイヤー":"크로스파이어",
 "球持ち○":"볼유지○","緩急○":"완급○","対ランナー〇":"대주자○",
 "対ランナー":"대주자","真っスラ":"직슬라","ナチュラルシュート":"내추럴슈트",
 "フライボールピッチャー":"플라이볼피처","ゴロピッチャー":"땅볼피처",
 "荒れ球":"난폭구","投打躍動":"투타약동","立ち上がり○":"초반안정○",
 "全開":"만개","要所○":"요소○","速球中心":"속구중심","変化球中心":"변화구중심",
 "テンポ○":"템포○","投球位置右":"투구위치우","投球位置左":"투구위치좌",
 "投手位置右":"투구위치우","投手位置左":"투구위치좌",
 "チャンス":"찬스","対左投手":"좌투수전","盗塁":"도루","走塁":"주루","送球":"송구",
 "調子安定（野手）":"상태안정(야수)","調子極端（野手）":"상태극단(야수)",
 "ケガしにくさ":"부상방지",
 "アベレージヒッター":"어베리지히터","パワーヒッター":"파워히터",
 "広角打法":"광각타법","内野安打○":"내야안타○","流し打ち":"밀어치기",
 "プルヒッター":"풀히터","粘り打ち":"끈기타법","バント○":"번트○",
 "バント職人":"번트장인","初球○":"초구○","代打○":"대타○",
 "チャンスメーカー":"찬스메이커","ヘッドスライディング":"헤드슬라이딩",
 "ホーム突入":"홈돌입","ホーム死守":"홈사수","レーザービーム":"레이저빔",
 "守備職人":"수비장인","キャッチャー":"캐처","固め打ち":"몰아치기",
 "逆境○":"역경○","満塁安打男":"만루안타맨","満塁本塁打男":"만루홈런맨",
 "サヨナラ安打男":"끝내기안타맨","サヨナラ本塁打男":"끝내기홈런맨",
 "ローボールヒッター":"로우볼히터","ハイボールヒッター":"하이볼히터",
 "威圧感（野手）":"위압감(야수)","いぶし銀":"숨은명수","プレッシャーラン":"프레셔런",
 "ムード○":"무드○","ムード×":"무드×","対エース○":"대에이스○","意外性":"의외성",
 "かく乱":"교란","インコースヒッター":"인코스히터","アウトコースヒッター":"아웃코스히터",
 "対変化球○":"대변화구○","ダメ押し":"쐐기타","ラインドライブ":"라인드라이브",
 "カット打ち":"커트타법","対ストレート〇":"대직구○","決勝打":"결승타",
 "マルチ弾":"멀티포","リベンジ":"리벤지","窮地〇":"궁지○",
 "チームプレイ○":"팀플레이○","チームプレイ×":"팀플레이×",
 "強振多用":"강타위주","ミート多用":"미트위주","積極打法":"적극타법","慎重打法":"신중타법",
 "積極盗塁":"적극도루","慎重盗塁":"신중도루","積極走塁":"적극주루","積極守備":"적극수비",
 "選球眼":"선구안","高速チャージ":"고속차지","悪球打ち":"악구타법",
 "春男":"춘맨","夏男":"하맨","秋男":"추맨","お祭り男":"축제맨",
 "強心臓":"강심장","ノミの心臓":"벼룩심장",
 "左キラー（投手）":"좌완킬러(투)","左キラー（野手）":"좌완킬러(야)","左キラー":"좌완킬러",
 "不屈の魂":"불굴의혼","ガラスのハート":"유리멘탈","鉄人":"철인","怪童":"괴동",
 "驚異の切れ味":"경이적예리함","走者釘付":"주자속박","ガソリンタンク":"가솔린탱크",
 "鉄腕":"철완","怪物球威":"괴물구위","本塁打厳禁":"홈런엄금","ドクターＫ":"닥터K",
 "精密機械":"정밀기계","変幻自在":"변환자재","勝負師":"승부사","球界の頭脳":"야구두뇌",
 "電光石火":"전광석화","高速ベースラン":"고속베이스런","ストライク送球":"스트라이크송구",
 "安打製造機":"안타제조기","アーチスト":"아티스트","芸術的流し打ち":"예술적밀어치기",
 "一球入魂":"일구입혼","切り込み隊長":"돌격대장","扇風機":"선풍기",
 "恐怖の満塁男":"공포의만루맨","伝説のサヨナラ男":"전설의끝내기맨","代打の神様":"대타의신",
 "気迫ヘッド":"기백헤드","高速レーザー":"고속레이저","魔術師":"마술사","鉄の壁":"철의벽",
 "重戦車":"중전차","ささやき戦術":"속삭임전술","ハイスピンジャイロ":"하이스핀자이로",
 "勝利の星":"승리의별","ド根性":"왕근성","火事場の馬鹿力":"위기의괴력",
 "大番狂わせ":"대이변","終盤力":"종반력","広角砲":"광각포","バズーカ送球":"바주카송구",
 "メッタ打ち":"무차별타","ロケットスタート":"로켓스타트","高球必打":"고구필타",
 "低球必打":"저구필타","内角必打":"몸쪽필타","外角必打":"바깥필타",
 "精神的支柱":"정신적지주","内角無双":"몸쪽무쌍","エースキラー":"에이스킬러",
 "主砲キラー":"주포킬러","引っ張り屋":"당겨치기왕","トリックスター":"트릭스터",
 "ギアチェンジ":"기어체인지","逆襲":"역습","ヒートアップ":"히트업","闘魂":"투혼",
 "ディレイドアーム":"딜레이드암","クロスキャノン":"크로스캐논","暴れ球":"난동구",
 "超投打躍動":"초투타약동","トップギア":"톱기어","完全燃焼":"완전연소",
 "渾身の決勝打":"혼신의결승타","国際大会○":"국제대회○","国際大会×":"국제대회×",
 "軽い球":"경쾌구","抜け球":"빠짐구","スロースターター":"슬로스타터","寸前×":"막판×",
 "一発":"한방","短気":"다혈질","四球":"사구","力配分":"힘배분","勝ち運":"승운",
 "負け運":"패운","乱調":"난조","三振":"삼진","併殺":"병살",
 "威圧感（投手）":"위압감(투수)","満塁男":"만루맨","サヨナラ男":"끝내기맨",
 "対エース":"대에이스",
}

def enc(s):
    return len(s.encode('utf-8'))

def fit(s, maxb, fallback=None):
    if enc(s) <= maxb:
        return s
    if fallback and enc(fallback) <= maxb:
        return fallback
    # last resort: hard trim (shouldn't normally trigger)
    while enc(s) > maxb and len(s) > 0:
        s = s[:-1]
    return s

TRANS = {}

PMSIGN = {'＋':'+','－':'-'}
DIGITS = {'１':'1','２':'2','３':'3','４':'4','５':'5'}

for s in slots:
    i = s['i']; jp = s['jp']; mb = s['maxb']
    # direct ability name match
    if jp in ABILITY:
        TRANS[i] = fit(ABILITY[jp], mb)
        continue
    # ability + fullwidth ±N suffix, e.g. 打たれ強さ＋１
    m = re.match(r'^(.*?)([＋－])([１２３４５])$', jp)
    if m and m.group(1) in ABILITY:
        sign = PMSIGN[m.group(2)]; num = DIGITS[m.group(3)]
        TRANS[i] = fit(ABILITY[m.group(1)] + sign + num, mb)
        continue
    m = re.match(r'^(.*)の必勝本$', jp)
    if m and m.group(1) in ABILITY:
        TRANS[i] = fit(ABILITY[m.group(1)] + "의 필승본", mb, ABILITY[m.group(1)]+"필승본")
        continue
    m = re.match(r'^(.*)の本$', jp)
    if m and m.group(1) in ABILITY:
        TRANS[i] = fit(ABILITY[m.group(1)] + "의 책", mb, ABILITY[m.group(1)]+"책")
        continue
    m = re.match(r'^(.*)になります。?$', jp)
    if m and m.group(1) in ABILITY:
        TRANS[i] = fit(ABILITY[m.group(1)] + "이(가) 됩니다.", mb, ABILITY[m.group(1)]+"화.")
        continue
    m = re.match(r'^(.*)になった。?$', jp)
    if m and m.group(1) in ABILITY:
        TRANS[i] = fit(ABILITY[m.group(1)] + "이(가) 되었다.", mb, ABILITY[m.group(1)]+"화.")
        continue

import sys, os
sys.path.insert(0, r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
from trans2 import TRANS2
TRANS.update(TRANS2)

print("auto-templated+manual:", len(TRANS))
json.dump(TRANS, open('_auto_trans.json',"w",encoding="utf-8"), ensure_ascii=False, indent=0)

# list unresolved
unresolved = [s for s in slots if s['i'] not in TRANS]
print("unresolved:", len(unresolved))
with open('_unresolved.jsonl',"w",encoding="utf-8") as f:
    for s in unresolved:
        f.write(json.dumps({"i":s['i'],"jp":s['jp'],"maxb":s['maxb']}, ensure_ascii=False)+"\n")

# ---------------------------------------------------------------
# Validation: byte length, newline count, %-token count, <TAG> count
# ---------------------------------------------------------------
import collections

def count_nl(s): return s.count('\n')
def count_pct(s): return len(re.findall(r'%[sd]', s))
def count_tags(s): return sorted(re.findall(r'<[^>]+>', s))

import sys
sys.path.insert(0, r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
from trans3_fix import FIX
TRANS.update(FIX)

# generic auto-shrink: strip internal spaces if it helps fit
for sl in slots:
    i = sl['i']; mb = sl['maxb']
    ko = TRANS[i]
    if enc(ko) > mb:
        squeezed = ko.replace(' ', '')
        if enc(squeezed) <= mb:
            TRANS[i] = squeezed

overflow = []
mismatch = []
for sl in slots:
    i = sl['i']; jp = sl['jp']; mb = sl['maxb']
    ko = TRANS[i]
    b = enc(ko)
    if b > mb:
        overflow.append((i, jp, ko, b, mb))
    if count_nl(jp) != count_nl(ko):
        mismatch.append((i, 'nl', jp, ko))
    if count_pct(jp) != count_pct(ko):
        mismatch.append((i, 'pct', jp, ko))
    if count_tags(jp) != count_tags(ko):
        mismatch.append((i, 'tag', jp, ko))

print("overflow count:", len(overflow))
print("mismatch count:", len(mismatch))
with open('_overflow.jsonl',"w",encoding="utf-8") as f:
    for x in overflow:
        f.write(json.dumps(x, ensure_ascii=False)+"\n")
with open('_mismatch.jsonl',"w",encoding="utf-8") as f:
    for x in mismatch:
        f.write(json.dumps(x, ensure_ascii=False)+"\n")

# write final output
out = [{"i": i, "ko": TRANS[i]} for i in [s['i'] for s in slots]]
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print("wrote", len(out), "entries to", OUT)
