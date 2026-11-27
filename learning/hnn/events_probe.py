"""Measure what the trajectories say about enemy-enemy contact and explosions (no engine code)."""
import argparse, json, collections, numpy as np
parser = argparse.ArgumentParser()
parser.add_argument("data", help="path to physics training NDJSON")
args = parser.parse_args()
games=collections.defaultdict(list)
with open(args.data) as f:
    for line in f:
        r=json.loads(line)
        if "ph" in r: games[r["s"]].append(r)

def overlap(a,b):   # visible boxes: (x,y,size)
    return a[0]+a[2]>b[0] and a[1]+a[2]>b[1] and a[0]<b[0]+b[2] and a[1]<b[1]+b[2]

# 1. blasts: track by centre
blast_life=[]; first_size=[]; growth=collections.Counter(); peak=[]
for frames in games.values():
    live={}
    for r in frames:
        seen=set()
        for e in r["ph"]:
            if e[5]!=-1: continue
            c=(round(e[0]+e[4]/2,1),round(e[1]+e[4]/2,1))
            seen.add(c)
            if c not in live: live[c]=[r["f"],[e[4]]]; first_size.append(e[4])
            else: live[c][1].append(e[4])
        for c in [c for c in live if c not in seen]:
            blast_life.append(live.pop(c))
print("blasts tracked:",len(blast_life),"first-seen size histogram:",collections.Counter(round(s) for s in first_size).most_common(5))
sizes=[b[1] for b in blast_life if len(b[1])>5]
if sizes:
    s=sizes[0]; print("example size series:",[round(x,1) for x in s][:70])
    print("typical lifetime (frames):",int(np.median([len(b[1]) for b in blast_life])),"peak size median",np.median([max(b[1]) for b in blast_life]))
    inc=[round(x[i+1]-x[i],2) for x in sizes for i in range(len(x)-1)]
    print("per-frame size change histogram:",collections.Counter(inc).most_common(6))

# 2. do overlapping non-blast enemy pairs vanish next frame?
stats=collections.Counter()
for frames in games.values():
    for a,b in zip(frames,frames[1:]):
        if b["f"]!=a["f"]+1: continue
        E=[e for e in a["ph"] if e[5]>=0]; N=[e for e in b["ph"]]
        for i in range(len(E)):
            for j in range(i+1,len(E)):
                ei,ej=E[i],E[j]
                if overlap((ei[0],ei[1],ei[4]),(ej[0],ej[1],ej[4])):
                    # does each still exist next frame? match by predicted position
                    def alive(e):
                        g=np.array([e[0]+e[2]*e[6],e[1]+e[3]*e[6]])
                        return any(abs(n[0]-g[0])<2.5 and abs(n[1]-g[1])<2.5 and n[5]==e[5] for n in N)
                    stats[(ei[5],ej[5],"both vanish" if not alive(ei) and not alive(ej) else "some survive")]+=1
for k,v in sorted(stats.items(), key=lambda kv:-kv[1])[:8]: print(" overlap pair (kinds",k[0],k[1],"):",k[2],v)
