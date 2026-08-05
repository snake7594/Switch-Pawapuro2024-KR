# -*- coding: utf-8 -*-
"""UNCDFONT 글리프 테이블 파싱 + 원본/A/B 비교.
   레코드: +0x3C부터 12B {u32 code, u32 offset(청크상대), u32 metrics}, 개수 @+0x20."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
def u32(b,o): return struct.unpack_from("<I",b,o)[0]

def find_uncd(b):
    CHK=32; di=u32(b,CHK+16); ds=u32(b,CHK+20)
    pos=CHK+di; hi=CHK+ds; out=[]
    while pos<hi:
        ts=u32(b,pos+8); ct=b[pos+16:pos+24]
        if ts==0 or pos+ts>len(b): break
        if ct==b"UNCDFONT": out.append((pos,ts))
        pos+=ts
    return out

def parse_font(b, p, ts):
    magic=b[p:p+4].decode()
    n=u32(b,p+0x20); w=u32(b,p+0x24); h=u32(b,p+0x28); n2=u32(b,p+0x2c)
    recs=[]
    rp=p+0x3c
    for i in range(n):
        code=u32(b,rp); off=u32(b,rp+4); met=u32(b,rp+8)
        recs.append((code,off,met)); rp+=12
    gsz=w*h//2
    return dict(magic=magic,p=p,ts=ts,n=n,n2=n2,w=w,h=h,gsz=gsz,recs=recs,table_end=rp)

def load(path):
    b=open(path,'rb').read()
    fonts=[parse_font(b,p,ts) for p,ts in find_uncd(b)]
    return b,fonts

O_b,O_f=load("COMMON_2D-o.CHK")
A_b,A_f=load("COMMON_2D-한글폰트삽입.CHK")
B_b,B_f=load("repack_in/COMMON_2D.CHK")

for fi in range(len(O_f)):
    fo,fa,fb=O_f[fi],A_f[fi],B_f[fi]
    print(f"\n========== {fo['magic']} ({fo['w']}x{fo['h']}, 글리프 {fo['n']}, n2={fo['n2']}, gsz={fo['gsz']}) ==========")
    print(f"  테이블 끝=+0x{fo['table_end']-fo['p']:x}  첫 글리프 off=0x{fo['recs'][4][1] if len(fo['recs'])>4 else 0:x}")
    # 레코드(인덱스) 차이
    for lbl,fx in (("A",fa),("B",fb)):
        assert fx['n']==fo['n'], f"{lbl} 글리프 수 다름!"
        d_code=[i for i in range(fo['n']) if fo['recs'][i][0]!=fx['recs'][i][0]]
        d_off =[i for i in range(fo['n']) if fo['recs'][i][1]!=fx['recs'][i][1]]
        d_met =[i for i in range(fo['n']) if fo['recs'][i][2]!=fx['recs'][i][2]]
        print(f"  [{lbl}] 코드 다름={len(d_code)}  오프셋 다름={len(d_off)}  메트릭 다름={len(d_met)}")
        for i in d_code[:6]:
            print(f"      code[{i}]: U+{fo['recs'][i][0]:04X} -> U+{fx['recs'][i][0]:04X}")
        for i in d_off[:6]:
            print(f"      off[{i}] (U+{fo['recs'][i][0]:04X}): 0x{fo['recs'][i][1]:x} -> 0x{fx['recs'][i][1]:x}")
        for i in d_met[:6]:
            print(f"      met[{i}] (U+{fo['recs'][i][0]:04X}): 0x{fo['recs'][i][2]:x} -> 0x{fx['recs'][i][2]:x}")
    # 비트맵 차이 (원본 오프셋 기준, 동일 코드 레코드)
    for lbl,fx,xb in (("A",fa,A_b),("B",fb,B_b)):
        changed=[]
        for i in range(fo['n']):
            co,oo,_=fo['recs'][i]; cx,ox,_=fx['recs'][i]
            if oo==0 or ox==0: continue
            g_o=O_b[fo['p']+oo : fo['p']+oo+fo['gsz']]
            g_x=xb[fx['p']+ox : fx['p']+ox+fx['gsz']]
            if g_o!=g_x: changed.append((i,co))
        print(f"  [{lbl}] 비트맵 변경 글리프: {len(changed)}개")
        # 코드 범위 요약
        if changed:
            codes=[c for _,c in changed]
            import collections
            rng=collections.Counter()
            for c in codes:
                if 0x4E00<=c<=0x9FFF: rng['CJK한자']+=1
                elif 0xAC00<=c<=0xD7A3: rng['한글']+=1
                elif 0x3040<=c<=0x30FF: rng['가나']+=1
                elif c<0x100: rng['라틴']+=1
                else: rng[f'기타(U+{c:04X}대)']+=1
            print(f"        범위: {dict(rng)}")
