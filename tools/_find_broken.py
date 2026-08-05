# -*- coding: utf-8 -*-
"""STRING 성장으로 크기 변동 + 이미지(NX SUR) 포함 CHK 식별 → 깨진 이미지 CHK 목록."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
RES="RES_추출원본"

def has_chunks(b):
    return (b.find(b'STRING')>=0, b.find(b'NX  SUR ')>=0)

def string_pos(b): return b.find(b'STRING')
def first_sur_after(b, after):
    p=b.find(b'NX  SUR ', after)
    return p

grown=[]      # STRING 커진 것
grown_img=[]  # STRING 커짐 + 이미지 있음
same=0; scan_or_nochange=0
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
print(f"검사 대상 {len(files)}개")
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o): continue
    so=os.path.getsize(o); sk=os.path.getsize(k)
    if sk==so:
        scan_or_nochange+=1; continue
    # 크기 변동 = STRING 재구성으로 성장/축소
    ob=open(o,'rb').read()
    has_str, has_img = has_chunks(ob)
    sp=string_pos(ob)
    sur=ob.find(b'NX  SUR ')
    img_after_string = has_img and has_str and sur>sp
    grown.append((fn, so, sk, sk-so, has_str, has_img, img_after_string))
    if img_after_string:
        grown_img.append((fn, so, sk, sk-so, sp, sur))

print(f"\n크기변동 CHK: {len(grown)}개")
print(f"그중 이미지(NX SUR)가 STRING 뒤에 있는 것(=이미지 손상 위험): {len(grown_img)}개")
print("\n=== 이미지 손상 위험 CHK (상위 30) ===")
for fn,so,sk,d,sp,sur in sorted(grown_img, key=lambda x:-abs(x[3]))[:30]:
    print(f"  {fn:32s} 원본{so}→패치{sk} (Δ{d:+d})  STRING@0x{sp:x} SUR@0x{sur:x}")

# 크기변동인데 이미지 없는 것(안전)도 개수만
safe_grown=[g for g in grown if not g[6]]
print(f"\n크기변동+이미지없음(안전): {len(safe_grown)}개")
print(f"크기불변(스캔/무변경): {scan_or_nochange}개")
