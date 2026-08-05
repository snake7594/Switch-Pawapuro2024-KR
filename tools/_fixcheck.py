import json

def blen(s):
    n = 0
    for ch in s:
        n += 1 if ord(ch) < 128 else 3
    return n

data = json.load(open('_scene_batch/b274.json', encoding='utf-8'))
maxb = {}
for scene in data:
    for line in scene['lines']:
        if 'i' in line:
            maxb[line['i']] = line['maxb']

out = json.load(open('_scene_tr_out/b274.json', encoding='utf-8'))

over = []
for o in out:
    b = blen(o['ko'])
    if b > maxb[o['i']]:
        over.append((o['i'], b, maxb[o['i']], o['ko']))

with open('_over3.txt', 'w', encoding='utf-8') as f:
    f.write(f"count={len(over)}\n")
    for x in over:
        f.write(f"{x[0]}\t{x[1]}/{x[2]}\t{x[3]}\n")

ids = [o['i'] for o in out]
missing = [i for i in maxb if i not in ids]
extra = [i for i in ids if i not in maxb]
dupes = [i for i in set(ids) if ids.count(i) > 1]
with open('_status.txt', 'w', encoding='utf-8') as f:
    f.write(f"total_input={len(maxb)} total_output={len(ids)} unique={len(set(ids))}\n")
    f.write(f"missing={missing}\nextra={extra}\ndupes={dupes}\n")
