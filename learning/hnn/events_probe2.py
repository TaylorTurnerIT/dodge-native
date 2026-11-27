import argparse, json, collections
parser = argparse.ArgumentParser()
parser.add_argument("data", help="path to physics training NDJSON")
args = parser.parse_args()
games=collections.defaultdict(list)
with open(args.data) as f:
    for line in f:
        r=json.loads(line)
        if "ph" in r: games[r["s"]].append(r)
def overlap(a,b): return a[0]+a[4]>b[0] and a[1]+a[4]>b[1] and a[0]<b[0]+b[4] and a[1]<b[1]+b[4]
def exists(e,frame):
    g=(e[0]+e[2]*e[6]*(1+0), e[1]+e[3]*e[6])
    return any(n[5]==e[5] and abs(n[0]-g[0])<3.5 and abs(n[1]-g[1])<3.5 for n in frame["ph"])
out=collections.Counter(); delay=collections.Counter()
for frames in games.values():
    for k in range(len(frames)-4):
        a=frames[k]
        if any(frames[k+d]["f"]!=a["f"]+d for d in (1,2,3,4)): continue
        E=[e for e in a["ph"] if e[5]>=0 and 1<=e[0]<=127 and 1<=e[1]<=127]
        for i in range(len(E)):
            for j in range(i+1,len(E)):
                if overlap(E[i],E[j]):
                    # first frame offset at which either is gone
                    gone=None
                    for d in (1,2,3,4):
                        if not exists(E[i],frames[k+d]) or not exists(E[j],frames[k+d]): gone=d; break
                        # advance guess crudely: compare against frame d using same-start position is wrong beyond d=1,
                        # so only the first step is trusted
                        break
                    out[(int(E[i][5]),int(E[j][5]),"gone next frame" if gone==1 else "present next frame")]+=1
for k,v in sorted(out.items(), key=lambda kv:-kv[1])[:8]: print(k,v)
